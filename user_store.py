# -*- coding: utf-8 -*-
"""用户信息存储层：文件（JSON）与 MySQL 双后端，同一套接口、按配置切换。

为什么要多这一层（而不是直接把 data/users.json 换成 MySQL）——
本项目有三个运行场景，对存储的要求互相矛盾：
1. 本地开发 / 答辩演示：希望用 MySQL（也是「用户管理系统」的落点）；
2. Streamlit Community Cloud：云端服务器**连不到**本机 127.0.0.1 的 MySQL，只能用文件；
3. PyInstaller 打包的 exe：别人的电脑上没装 MySQL，也只能用文件。
于是把「读写用户」抽成统一接口、两种实现，由 secrets 里的
[storage] backend 决定用哪个；**缺省是 json**，保证 2、3 两个场景的行为一个字都不变。

三条设计约定：
- 字段名各说各话、边界处转换：本模块统一用 password_hash，而
  streamlit-authenticator 要求字段名叫 password，转换在 auth.py 里显式做，
  两边都不必迁就对方的叫法。
- 时间统一存 UTC：云端是 UTC、本地是东八区，混着存必然对不上；
  展示时用 fmt_local() 换成本机时区。
- 禁用不等于删除：status 置为 disabled，由 auth.py 把该账号从交给认证库的名单里
  过滤掉，于是它在认证库眼里根本不存在、自然登不进来——不用去改认证库的逻辑。

凭据位置：MySQL 连接参数只从 st.secrets 的 [mysql] 段读，绝不写进代码；
本仓库是公开的，.streamlit/secrets.toml 已被 .gitignore 排除。
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"
VALID_STATUS = (STATUS_ACTIVE, STATUS_DISABLED)

# 单次连接超时（秒）。MySQL 挂掉时不能让每次页面重跑都长时间卡住。
CONNECT_TIMEOUT = 3

# JSON 后端的登录日志上限：文件存储不适合无限增长，滚动保留最近 N 条。
MAX_JSON_LOGS = 500

# 允许被写入的列（白名单）。SQL 列名不能用参数占位符，所以必须白名单校验，
# 不能把界面传进来的字段名直接拼进语句。
_WRITABLE_COLUMNS = (
    "email", "first_name", "last_name", "password_hash",
    "password_hint", "roles", "status",
)

DEFAULT_MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "database": "pop_music",
}

SCHEMA_STATEMENTS = (
    # utf8mb4：用户名与姓名可能含中文、emoji
    """
    CREATE TABLE IF NOT EXISTS users (
        username      VARCHAR(64)  NOT NULL,
        email         VARCHAR(255) DEFAULT NULL,
        first_name    VARCHAR(64)  DEFAULT NULL,
        last_name     VARCHAR(64)  DEFAULT NULL,
        password_hash VARCHAR(255) NOT NULL,
        password_hint VARCHAR(255) DEFAULT NULL,
        roles         TEXT         DEFAULT NULL,
        status        VARCHAR(16)  NOT NULL DEFAULT 'active',
        created_at    DATETIME     DEFAULT NULL,
        updated_at    DATETIME     DEFAULT NULL,
        last_login_at DATETIME     DEFAULT NULL,
        PRIMARY KEY (username)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS login_log (
        id       BIGINT      NOT NULL AUTO_INCREMENT,
        username VARCHAR(64) NOT NULL,
        login_at DATETIME    NOT NULL,
        ip       VARCHAR(64)  DEFAULT NULL,
        success  TINYINT(1)  NOT NULL DEFAULT 1,
        PRIMARY KEY (id),
        KEY idx_login_log_username (username),
        KEY idx_login_log_login_at (login_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


class StoreConfigError(RuntimeError):
    """MySQL 后端配置缺失或不完整（例如 secrets 里没填密码）。"""


class StoreUnavailableError(RuntimeError):
    """MySQL 连不上（服务没开、密码错、库不存在等）。"""


class QueryError(RuntimeError):
    """SQL 查询出错（语法错、被只读会话拒绝等）。原样携带数据库的报错信息。"""


# --------------------------------------------------- 数据表前端（网格口径）--

ROLE_ADMIN = "admin"
ROLE_USER = "user"
# 网格里的角色只提供这几个组合：它们是仅有的有意义取值。
# 用下拉而不是自由文本，就不会出现 "adimn" 这种手滑打错的角色名
# ——打错的角色名不会报错，只会让权限判断静默失效。
ROLE_CHOICES = (ROLE_USER, ROLE_ADMIN, f"{ROLE_ADMIN}, {ROLE_USER}")

STATUS_LABELS = {STATUS_ACTIVE: "启用中", STATUS_DISABLED: "已禁用"}
STATUS_BY_LABEL = {label: value for value, label in STATUS_LABELS.items()}

# st.data_editor 网格的列。定义在这里而不是 app.py，因为「网格长什么样」
# 是前端与数据库之间的契约：写计划（plan_user_changes）要按它解析。
GRID_ROW_COLUMNS = ("删除?", "用户名", "状态", "角色", "邮箱", "姓", "名",
                    "创建时间", "最后登录")

# 查询页的示例按钮（点一下填入输入框）。刻意全写成只读语句——
# 会话虽然已被数据库强制只读，示例本身也该给出正确示范；
# 时间条件用 UTC_TIMESTAMP() 对齐库里的 UTC 存储口径。
QUERY_EXAMPLES = {
    "用户表": "SELECT * FROM users ORDER BY username",
    "登录日志": "SELECT * FROM login_log ORDER BY login_at DESC LIMIT 20",
    "最近 7 天登录统计":
        "SELECT username, COUNT(*) AS 登录次数, SUM(success) AS 成功次数 "
        "FROM login_log "
        "WHERE login_at >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 7 DAY) "
        "GROUP BY username ORDER BY 登录次数 DESC",
    "表结构": "DESCRIBE users",
}


def _clean_text(value) -> str:
    """None / NaN 一律归一成空串。

    NaN 检查用「自反不等」（NaN != NaN 为真），不用为这一个判断引入 pandas。
    不归一的话 str(nan) 会得到字符串 "nan"，把用户的邮箱悄悄改成 "nan"。
    """
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip()


def roles_to_label(roles) -> str:
    """角色列表 → 网格里的显示文本（"admin, user"）。"""
    return ", ".join(norm_roles(roles))


def label_to_roles(label) -> list[str]:
    """网格里的显示文本 → 角色列表。"""
    return [r.strip() for r in _clean_text(label).split(",") if r.strip()]


def grid_row(username: str, record: dict) -> dict:
    """存储记录 → 网格行（中文列名，与 GRID_ROW_COLUMNS 一一对应）。"""
    return {
        "删除?": False,
        "用户名": username,
        "状态": STATUS_LABELS.get(record.get("status") or STATUS_ACTIVE, "启用中"),
        "角色": roles_to_label(record.get("roles")),
        "邮箱": record.get("email") or "",
        "姓": record.get("last_name") or "",
        "名": record.get("first_name") or "",
        "创建时间": fmt_local(record.get("created_at")),
        "最后登录": fmt_local(record.get("last_login_at")),
    }


@dataclass
class UserChangePlan:
    """网格改动翻译成数据库动作的结果。errors 非空时一件都不该执行。"""

    updates: list = field(default_factory=list)   # [(用户名, 待写字段 dict)]
    deletes: list = field(default_factory=list)   # [用户名]
    errors: list = field(default_factory=list)    # [原因]，一条一行给页面显示

    @property
    def has_changes(self) -> bool:
        return bool(self.updates or self.deletes)


def plan_user_changes(original: dict[str, dict], edited_rows, *,
                      me: str | None = None, presets=()) -> UserChangePlan:
    """对比「网格改出来的行」和「存储里的现状」，产出该执行的写库计划。

    为什么不把网格整个写回去：
    - 网格里混着只读展示列（创建时间等），用户通常也只改了一两格，
      逐字段比对后才写，不把没变的数据发一遍；
    - 更重要的是「不能删自己」「不能把自己降级/禁用」这类护栏必须集中在
      **数据库动作之前**拦下——带着错误写库再回滚，不如根本不发这条 SQL。
    """
    plan = UserChangePlan()
    preset_set = set(presets or ())
    seen: set[str] = set()

    for row in edited_rows:
        username = _clean_text(row.get("用户名"))
        if not username:
            plan.errors.append("网格里有一行没有用户名，无法处理")
            continue
        if username in seen:
            plan.errors.append(f"「{username}」在网格里出现了不止一次")
            continue
        seen.add(username)

        if username in preset_set:
            plan.errors.append(f"「{username}」是 secrets 预置账号，页面改不了"
                               "（改了下次加载也会被 secrets 覆盖回去）")
            continue
        if username not in original:
            plan.errors.append(f"「{username}」不在存储里（可能刚被删除），请刷新页面")
            continue

        # 勾了删除就只删不改——同时改了字段也没有意义
        if row.get("删除?") is True or row.get("删除?") == "True":
            if username == me:
                plan.errors.append("不能删除当前登录的账号")
            else:
                plan.deletes.append(username)
            continue

        record = original[username]
        fields: dict = {}
        for grid_col, db_col in (("邮箱", "email"), ("姓", "last_name"), ("名", "first_name")):
            value = _clean_text(row.get(grid_col))
            if value != (record.get(db_col) or ""):
                fields[db_col] = value

        status = STATUS_BY_LABEL.get(_clean_text(row.get("状态")))
        if status is None:
            plan.errors.append(f"「{username}」的状态取值不认识：{row.get('状态')!r}")
            continue
        if status != (record.get("status") or STATUS_ACTIVE):
            if username == me and status == STATUS_DISABLED:
                plan.errors.append("不能禁用当前登录的账号")
                continue
            fields["status"] = status

        roles = label_to_roles(row.get("角色"))
        if not roles:
            plan.errors.append(f"「{username}」至少要保留一个角色")
            continue
        if sorted(roles) != sorted(norm_roles(record.get("roles"))):
            if username == me and ROLE_ADMIN not in roles:
                plan.errors.append("不能取消自己的管理员角色（否则你将无法再进入本页）")
                continue
            fields["roles"] = roles

        if fields:
            plan.updates.append((username, fields))

    return plan


# ------------------------------------------------------------------ 路径与时间 --

def resolve_dirs() -> tuple[Path, Path]:
    """返回 (只读资源目录, 可写基准目录)。

    源码运行：两者都是项目根目录。
    PyInstaller 打包运行：资源（app.py、结果表）在解包临时目录 _MEIPASS，
    可写文件（.streamlit/secrets.toml、data/users.json）在 exe 所在目录——
    这样用户把 exe 拷到哪里，注册账号就持久化到哪里。

    放在本模块是因为「可写数据文件放哪」属于存储层的事；auth.py 再把它转出去，
    这样 `from auth import resolve_dirs` 的老写法（app.py 在用）不受影响。
    """
    if getattr(sys, "frozen", False):
        resource = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        base = Path(sys.executable).parent
    else:
        resource = base = Path(__file__).resolve().parent
    return resource, base


RESOURCE_DIR, ROOT = resolve_dirs()
DATA_DIR = ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
LOGIN_LOG_FILE = DATA_DIR / "login_log.json"


def now_utc() -> datetime:
    """当前时间（UTC，naive）。库里用 DATETIME 存，JSON 里存同样的 ISO 字符串。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_dt(value) -> datetime | None:
    """把存储层读出的时间统一成「带 UTC 时区的 datetime」，失败返回 None。

    两种后端给的形态不同：MySQL 给 datetime 对象，JSON 给 ISO 字符串。
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fmt_local(value) -> str:
    """转成本机时区展示（存的是 UTC，直接显示会差 8 小时）。"""
    dt = parse_dt(value)
    if dt is None:
        return "—"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def norm_roles(value) -> list[str]:
    """角色统一成字符串列表：兼容 None、["admin"]、"admin"、"admin,user"。

    先判 None 再 str()：直接 str(None) 会得到字符串 "None"，
    那会让「没有角色」变成一个叫 None 的角色混进权限判断里。
    """
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [r.strip() for r in value.split(",") if r.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(r).strip() for r in value if r is not None and str(r).strip()]
    return [str(value)]


def parse_roles_column(value) -> list[str]:
    """解析从 MySQL 的 roles 列读出来的值（那一列存的是 JSON 文本）。

    必须先按 JSON 解析，再退回逗号分隔。否则 '["user"]' 这种字符串会被
    norm_roles 当成「逗号分隔的角色名」，解析成 ['["user"]'] ——
    一个带引号和方括号的假角色名，于是权限判断永远不成立、管理员进不去管理页。
    这个 bug 是靠 test_user_store.py 的 MySQL 往返用例抓出来的。
    """
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return norm_roles(json.loads(text))
            except json.JSONDecodeError:
                pass
    return norm_roles(value)


def to_auth_entry(record: dict) -> dict:
    """存储层的记录 → streamlit-authenticator 要的凭据条目。

    认证库的字段名是 password（存 bcrypt 哈希），本模块叫 password_hash，
    转换只在这一处发生。多余字段（status、时间戳等）不带过去，
    免得认证库把它们当成用户属性到处复制。
    """
    entry = {
        "email": record.get("email") or "",
        "first_name": record.get("first_name") or "",
        "last_name": record.get("last_name") or "",
        "password": record.get("password_hash") or "",
        "roles": norm_roles(record.get("roles")),
    }
    if record.get("password_hint"):
        entry["password_hint"] = record["password_hint"]
    return entry


def _secret_section(name: str) -> dict:
    """读 st.secrets 的某个段；没有 secrets 或没这段时返回空字典（不抛异常）。

    非 Streamlit 环境（命令行脚本）里 st.secrets 也能读，但文件不存在时会抛错，
    所以一律 try 兜住。
    """
    try:
        import streamlit as st

        section = st.secrets.get(name, {})
    except Exception:
        return {}
    try:
        return {k: section[k] for k in section}
    except Exception:
        return {}


# ------------------------------------------------------------------- 文件后端 --

class JsonUserStore:
    """把用户写在 data/users.json、登录日志写在 data/login_log.json。

    沿用 auth.py 原来的文件格式（{"usernames": {...}}），
    只补上 status 与时间戳字段——老文件缺这些字段时按默认值读，向后兼容。
    """

    backend = "json"
    source_label = "文件"
    supports_sql = False
    note: str | None = None

    def __init__(self, users_file: Path | None = None, log_file: Path | None = None) -> None:
        self.users_file = Path(users_file) if users_file else USERS_FILE
        self.log_file = Path(log_file) if log_file else LOGIN_LOG_FILE

    # ---- 底层读写 ----
    def _read_json(self, path: Path, key: str) -> list | dict:
        if not path.exists():
            return [] if key == "logs" else {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return [] if key == "logs" else {}
        value = data.get(key)
        return value if isinstance(value, (list, dict)) else ([] if key == "logs" else {})

    def _write_json(self, path: Path, key: str, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({key: value}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> dict:
        return self._read_json(self.users_file, "usernames")

    def _save(self, usernames: dict) -> None:
        self._write_json(self.users_file, "usernames", usernames)

    def _record(self, username: str, raw: dict) -> dict:
        return {
            "username": username,
            "email": raw.get("email") or "",
            "first_name": raw.get("first_name") or "",
            "last_name": raw.get("last_name") or "",
            "password_hash": raw.get("password_hash") or raw.get("password") or "",
            "password_hint": raw.get("password_hint") or "",
            "roles": norm_roles(raw.get("roles")),
            "status": raw.get("status") or STATUS_ACTIVE,
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "last_login_at": raw.get("last_login_at"),
            "source": self.source_label,
        }

    # ---- 接口 ----
    def list_users(self) -> dict[str, dict]:
        return {u: self._record(u, raw) for u, raw in sorted(self._load().items())}

    def get_user(self, username: str) -> dict | None:
        raw = self._load().get(username)
        return self._record(username, raw) if raw else None

    def create_user(self, username: str, record: dict) -> None:
        usernames = self._load()
        if username in usernames:
            raise ValueError(f"用户名「{username}」已存在")
        entry = {
            "email": record.get("email") or "",
            "first_name": record.get("first_name") or "",
            "last_name": record.get("last_name") or "",
            "password_hash": record.get("password_hash") or "",
            "roles": norm_roles(record.get("roles")),
            "status": record.get("status") or STATUS_ACTIVE,
            "created_at": now_utc().isoformat(timespec="seconds"),
            "updated_at": now_utc().isoformat(timespec="seconds"),
            "last_login_at": None,
        }
        if record.get("password_hint"):
            entry["password_hint"] = record["password_hint"]
        usernames[username] = entry
        self._save(usernames)

    def update_user(self, username: str, fields: dict) -> None:
        usernames = self._load()
        if username not in usernames:
            raise ValueError(f"用户「{username}」不存在")
        entry = usernames[username]
        for key, value in fields.items():
            if key not in _WRITABLE_COLUMNS:
                continue
            if key == "roles":
                value = norm_roles(value)
            if key == "status" and value not in VALID_STATUS:
                raise ValueError(f"非法状态：{value}")
            entry[key] = value
        entry["updated_at"] = now_utc().isoformat(timespec="seconds")
        self._save(usernames)

    def set_password(self, username: str, password_hash: str) -> None:
        self.update_user(username, {"password_hash": password_hash})

    def set_status(self, username: str, status: str) -> None:
        self.update_user(username, {"status": status})

    def set_roles(self, username: str, roles) -> None:
        self.update_user(username, {"roles": roles})

    def delete_user(self, username: str) -> bool:
        usernames = self._load()
        if username not in usernames:
            return False
        del usernames[username]
        self._save(usernames)
        return True

    def record_login(self, username: str, success: bool, ip: str | None = None) -> None:
        logs = self._read_json(self.log_file, "logs")
        logs.insert(0, {
            "username": (username or "")[:64],
            "login_at": now_utc().isoformat(timespec="seconds"),
            "ip": ip,
            "success": bool(success),
        })
        self._write_json(self.log_file, "logs", logs[:MAX_JSON_LOGS])
        if success and username:
            usernames = self._load()
            if username in usernames:
                usernames[username]["last_login_at"] = now_utc().isoformat(timespec="seconds")
                self._save(usernames)

    def list_login_logs(self, limit: int = 200) -> list[dict]:
        logs = self._read_json(self.log_file, "logs")
        return [
            {
                "username": row.get("username") or "",
                "login_at": row.get("login_at"),
                "ip": row.get("ip") or "—",
                "success": bool(row.get("success")),
            }
            for row in logs[:limit]
        ]

    def ping(self) -> tuple[bool, str]:
        return True, f"文件存储可用（{self.users_file}）"

    def run_readonly_query(self, sql: str, max_rows: int = 500):
        """文件后端没有 SQL 引擎，查询页用它给出明确解释而不是报错。"""
        raise QueryError(
            "当前是文件后端（data/users.json），没有 SQL 可执行；"
            '把 secrets 里的 [storage] backend 改成 "mysql" 后，查询页才可用')


# ------------------------------------------------------------------ MySQL 后端 --

class MySqlUserStore:
    """MySQL 实现：接口与 JsonUserStore 完全一致，上层察觉不到差别。

    连接策略是「每次操作开一条短连接、用完就关」，不做连接池。
    理由：Streamlit 每次交互都会重跑脚本，长连接很容易在重跑之间变成
    失效连接（服务器超时断开），而本地 MySQL 建连只要几毫秒，
    简单正确比省这点开销重要。
    """

    backend = "mysql"
    source_label = "数据库"
    supports_sql = True
    note: str | None = None

    def __init__(self, params: dict) -> None:
        self.params = params
        self.database = params["database"]

    @classmethod
    def from_secrets(cls) -> MySqlUserStore:
        """从 st.secrets 的 [mysql] 段构造；配置不全时抛 StoreConfigError。"""
        cfg = _secret_section("mysql")
        if not cfg:
            raise StoreConfigError("secrets 里没有 [mysql] 段")
        params = {
            "host": str(cfg.get("host") or DEFAULT_MYSQL["host"]),
            "port": int(cfg.get("port") or DEFAULT_MYSQL["port"]),
            "user": str(cfg.get("user") or DEFAULT_MYSQL["user"]),
            "password": str(cfg.get("password") or ""),
            "database": str(cfg.get("database") or DEFAULT_MYSQL["database"]),
        }
        if not params["password"] or "REPLACE" in params["password"].upper():
            raise StoreConfigError("[mysql].password 还没填")
        return cls(params)

    @contextmanager
    def _connect(self, database: bool = True):
        """开一条连接；正常结束提交、出错回滚、无论如何关闭。"""
        try:
            import pymysql
            from pymysql.cursors import DictCursor
        except ImportError as exc:  # 只有走 MySQL 后端才需要这个依赖
            raise StoreUnavailableError(
                "没装 PyMySQL（pip install PyMySQL），无法使用 MySQL 后端"
            ) from exc

        try:
            conn = pymysql.connect(
                host=self.params["host"],
                port=self.params["port"],
                user=self.params["user"],
                password=self.params["password"],
                database=self.database if database else None,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=False,
                connect_timeout=CONNECT_TIMEOUT,
            )
        except Exception as exc:  # noqa: BLE001 - 连不上就是连不上，统一转成自己的异常
            raise StoreUnavailableError(str(exc)) from exc

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _row_to_record(self, row: dict) -> dict:
        return {
            "username": row.get("username") or "",
            "email": row.get("email") or "",
            "first_name": row.get("first_name") or "",
            "last_name": row.get("last_name") or "",
            "password_hash": row.get("password_hash") or "",
            "password_hint": row.get("password_hint") or "",
            "roles": parse_roles_column(row.get("roles")),
            "status": row.get("status") or STATUS_ACTIVE,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_login_at": row.get("last_login_at"),
            "source": self.source_label,
        }

    # ---- 接口 ----
    def list_users(self) -> dict[str, dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users ORDER BY username")
                rows = cur.fetchall()
        return {row["username"]: self._row_to_record(row) for row in rows}

    def get_user(self, username: str) -> dict | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
        return self._row_to_record(row) if row else None

    def create_user(self, username: str, record: dict) -> None:
        if self.get_user(username):
            raise ValueError(f"用户名「{username}」已存在")
        now = now_utc()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, email, first_name, last_name, "
                    "password_hash, password_hint, roles, status, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        username,
                        record.get("email") or "",
                        record.get("first_name") or "",
                        record.get("last_name") or "",
                        record.get("password_hash") or "",
                        record.get("password_hint") or None,
                        json.dumps(norm_roles(record.get("roles")), ensure_ascii=False),
                        record.get("status") or STATUS_ACTIVE,
                        now,
                        now,
                    ),
                )

    def update_user(self, username: str, fields: dict) -> None:
        sets, values = [], []
        for key, value in fields.items():
            if key not in _WRITABLE_COLUMNS:
                continue
            if key == "roles":
                value = json.dumps(norm_roles(value), ensure_ascii=False)
            if key == "status" and value not in VALID_STATUS:
                raise ValueError(f"非法状态：{value}")
            sets.append(f"`{key}` = %s")
            values.append(value)
        if not sets:
            return
        sets.append("`updated_at` = %s")
        values.append(now_utc())
        values.append(username)
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 存在性必须单独查，不能拿 UPDATE 的 rowcount 判断：
                # MySQL 的 rowcount 是「实际改动的行数」，新值与旧值完全相同时为 0，
                # 那样「保存了但内容没变」会被误报成「用户不存在」——
                # 管理页上就是点一下保存角色就弹一个假错误。
                cur.execute("SELECT 1 FROM users WHERE username = %s", (username,))
                if cur.fetchone() is None:
                    raise ValueError(f"用户「{username}」不存在")
                cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE username = %s", values)

    def set_password(self, username: str, password_hash: str) -> None:
        self.update_user(username, {"password_hash": password_hash})

    def set_status(self, username: str, status: str) -> None:
        self.update_user(username, {"status": status})

    def set_roles(self, username: str, roles) -> None:
        self.update_user(username, {"roles": roles})

    def delete_user(self, username: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE username = %s", (username,))
                return cur.rowcount > 0

    def record_login(self, username: str, success: bool, ip: str | None = None) -> None:
        """记一条登录日志；成功时顺带更新 last_login_at。

        两条写在同一事务里：日志写成功但时间没更新（或反过来）都是脏数据。
        注意预置账号（secrets 里）在库里没有对应行，UPDATE 影响 0 行属正常，
        不是错误——它的最后登录时间就只体现在日志表里。
        """
        now = now_utc()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO login_log (username, login_at, ip, success) "
                    "VALUES (%s, %s, %s, %s)",
                    ((username or "")[:64], now, ip, 1 if success else 0),
                )
                if success and username:
                    cur.execute(
                        "UPDATE users SET last_login_at = %s WHERE username = %s",
                        (now, username),
                    )

    def list_login_logs(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT username, login_at, ip, success FROM login_log "
                    "ORDER BY login_at DESC, id DESC LIMIT %s",
                    (int(limit),),
                )
                rows = cur.fetchall()
        return [
            {
                "username": row["username"],
                "login_at": row["login_at"],
                "ip": row["ip"] or "—",
                "success": bool(row["success"]),
            }
            for row in rows
        ]

    def ping(self) -> tuple[bool, str]:
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) AS n FROM users")
                    n = cur.fetchone()["n"]
            return True, f"连接正常，users 表 {n} 行"
        except StoreUnavailableError as exc:
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 - 表不存在等
            return False, str(exc)

    def run_readonly_query(self, sql: str, max_rows: int = 500):
        """在**只读会话**里执行一条查询，返回 (列名, 行, 是否截断, 提示)。

        只读不靠前端的字符串检查——那种检查只拦得住君子，拦不住拼错的关键字。
        真正的保证来自 SET SESSION TRANSACTION READ ONLY：这条连接里就算
        写出 UPDATE / DELETE / DROP TABLE，MySQL 也会在**服务端**直接拒绝，
        数据库层面没有可乘之机。前端的"必须 SELECT 开头"检查只负责
        给出友好的提前报错，不是安全边界。

        max_rows 限制返回行数：管理员随手写个无 LIMIT 的大查询，
        不能把 Streamlit 的页面撑爆。
        """
        text = (sql or "").strip().rstrip(";").strip()
        if not text:
            raise QueryError("查询语句为空")
        if ";" in text:
            raise QueryError("一次只允许执行一条语句：去掉多余的分号，或拆开逐条执行")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
                notes: list[str] = []
                try:
                    cur.execute("SET SESSION max_execution_time = 5000")
                    notes.append("查询超过 5 秒会被数据库主动终止")
                except Exception:  # noqa: BLE001 - 老版本没有这个变量
                    notes.append("当前 MySQL 不支持查询超时设置，大表请手动加 LIMIT")

                try:
                    cur.execute(text)
                except Exception as exc:  # noqa: BLE001 - 语法错/表名错等，原样给页面
                    raise QueryError(str(exc)) from exc

                if cur.description is None:
                    # 只读会话里写语句到不了这里（服务端已拒绝），防御性兜底
                    return [], [], False, notes
                columns = [d[0] for d in cur.description]
                rows = cur.fetchmany(max_rows)
                truncated = cur.fetchone() is not None
                return columns, rows, truncated, notes


# --------------------------------------------------------------------- 工厂 --

def get_store() -> JsonUserStore | MySqlUserStore:
    """按 secrets 的 [storage].backend 返回存储对象。

    缺省 json：云端与 exe 场景拿不到本机 MySQL，默认必须是文件后端，
    行为才与加这个功能之前完全一致。
    选了 mysql 但配置不全或连不上时**回退到文件**并挂一条 .note 说明原因——
    宁可降级可用，也不要让整个应用起不来（尤其登录页，那是唯一的入口）。
    """
    backend = str(_secret_section("storage").get("backend") or "json").strip().lower()
    if backend != "mysql":
        return JsonUserStore()

    try:
        store = MySqlUserStore.from_secrets()
    except StoreConfigError as exc:
        return _fallback_store(f"MySQL 后端配置不完整（{exc}）")

    ok, message = store.ping()
    if not ok:
        return _fallback_store(f"连不上 MySQL（{message}）")
    return store


def _fallback_store(reason: str) -> JsonUserStore:
    store = JsonUserStore()
    store.note = (
        f"{reason}，已临时回退到文件存储（data/users.json）："
        "登录与注册照常可用，但这些改动不会写进数据库。"
    )
    return store


# ------------------------------------------------------------------ 建表工具 --

def init_schema(params: dict, create_database: bool = True) -> list[str]:
    """建库（可选）+ 建表，返回执行过的步骤说明，供 scripts/init_db.py 打印。

    单独拿出来是因为建表要在「没有数据库」的状态下先连上去，与运行期
    （库已存在、只读写数据）的连接方式不同。
    """
    import pymysql
    from pymysql.cursors import DictCursor

    steps: list[str] = []
    database = params["database"]
    # 库名要拼进 DDL（标识符不能用参数占位符），所以先挡掉反引号与空白，
    # 免得配置里一个手滑就把语句拼坏。库名来自用户自己的 secrets，不是外部输入，
    # 这里防的是拼错而不是攻击。
    if not database or not database.replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"数据库名不合法（只允许字母、数字、下划线与连字符）：{database!r}")

    def connect(db=None):
        return pymysql.connect(
            host=params["host"], port=params["port"], user=params["user"],
            password=params["password"], database=db, charset="utf8mb4",
            cursorclass=DictCursor, autocommit=True, connect_timeout=CONNECT_TIMEOUT,
        )

    if create_database:
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            steps.append(f"数据库 `{database}` 已就绪（utf8mb4）")
        finally:
            conn.close()

    conn = connect(database)
    try:
        with conn.cursor() as cur:
            for statement in SCHEMA_STATEMENTS:
                cur.execute(statement)
            cur.execute("SHOW TABLES")
            tables = sorted(next(iter(row.values())) for row in cur.fetchall())
        steps.append(f"数据表已就绪：{'、'.join(tables)}")
    finally:
        conn.close()
    return steps

# -*- coding: utf-8 -*-
"""登录认证模块：登录门禁 + 注册用户持久化。

安全设计（这几点是刻意的，不是随手写的）：
1. **凭据绝不写进代码**：预置账号放在 st.secrets——本地是 .streamlit/secrets.toml，
   线上在 Streamlit Cloud 面板配置。因为本仓库是公开的，把密码写进 app.py 等于
   把密码发布到全网（还会被 GitHub 的密钥扫描机器人抓到）。
2. **密码只存 bcrypt 哈希**：注册时由 streamlit-authenticator 哈希，落盘的是哈希值，
   任何地方都不保存明文。
3. **注册用户必须自己落盘**：streamlit-authenticator 的 register_user 只更新内存里的
   凭据字典、不写文件，而 Streamlit 每次交互都会重跑脚本、重建 Authenticate 对象，
   不落盘的话用户注册完一刷新就没了。因此这里把新用户写入 data/users.json。
4. **线上持久化限制**：Streamlit Community Cloud 的文件系统是临时的，应用重启或
   重新部署后 data/users.json 会被重置，注册账号随之丢失（预置账号在 secrets 里不受影响）。
   要真正长期持久化需要接外部数据库（如 Supabase/PostgreSQL），属于后续扩展。
"""
from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth


def resolve_dirs() -> tuple[Path, Path]:
    """返回 (只读资源目录, 可写基准目录)。

    源码运行：两者都是项目根目录。
    PyInstaller 打包运行：资源（app.py、结果表）在解包临时目录 _MEIPASS，
    可写文件（.streamlit/secrets.toml、data/users.json）在 exe 所在目录——
    这样用户把 exe 拷到哪里，注册账号就持久化到哪里（比云端的临时文件系统可靠）。
    """
    if getattr(sys, "frozen", False):
        resource = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        base = Path(sys.executable).parent
    else:
        resource = base = Path(__file__).resolve().parent
    return resource, base


RESOURCE_DIR, ROOT = resolve_dirs()
USERS_FILE = ROOT / "data" / "users.json"

# 表单中文标签（库默认是英文，这里全部汉化）
LOGIN_FIELDS = {
    "Form name": "登录",
    "Username": "用户名",
    "Password": "密码",
    "Login": "登录",
    "Captcha": "验证码",
}
REGISTER_FIELDS = {
    "Form name": "注册新账号",
    "First name": "名",
    "Last name": "姓",
    "Email": "邮箱",
    "Username": "用户名",
    "Password": "密码",
    "Repeat password": "确认密码",
    "Password hint": "密码提示（可留空）",
    "Captcha": "验证码",
    "Register": "注册",
}
# 库的密码强度要求（8-20 位，含大小写、数字、特殊字符），汉化后提示给用户
PASSWORD_HINT_CN = (
    "密码要求：8~20 位，且至少包含 1 个大写字母、1 个小写字母、1 个数字、"
    "1 个特殊字符（如 !@#$%^&*）"
)


def _to_plain(obj):
    """把 st.secrets 的只读映射递归转成普通 dict/list。

    必须深拷贝：streamlit-authenticator 内部会往凭据字典里回写哈希后的密码
    （self.credentials['usernames'][user]['password'] = ...），
    而 st.secrets 返回的是只读对象，浅拷贝后嵌套层仍是只读的，会抛
    TypeError: Secrets does not support item assignment。
    """
    if isinstance(obj, Mapping):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    return obj


def _secret_config() -> dict:
    """读取 st.secrets 中的 auth 配置；未配置时返回空字典（不抛异常）。"""
    try:
        return _to_plain(st.secrets.get("auth", {}))
    except Exception:
        # 没有 secrets.toml 或线上未配置时会走到这里，属于预期情况
        return {}


def _load_registered() -> dict:
    """读取已注册用户（data/users.json），文件不存在或损坏时返回空。"""
    if not USERS_FILE.exists():
        return {}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data.get("usernames", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _save_registered(usernames: dict) -> None:
    """把注册用户写回 data/users.json。"""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(
        json.dumps({"usernames": usernames}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_credentials() -> tuple[dict, dict]:
    """合并「secrets 预置账号」与「文件里的注册用户」，返回 (凭据, 配置)。

    同名时以 secrets 预置账号为准，避免注册用户覆盖管理员账号。
    """
    cfg = _secret_config()
    base = dict(cfg.get("usernames", {}) or {})
    merged = dict(_load_registered())
    merged.update(base)  # 预置账号优先
    return {"usernames": merged}, cfg


def login_gate() -> tuple[stauth.Authenticate, str | None, str | None]:
    """登录门禁：未登录则渲染登录/注册页并中断脚本，已登录则返回认证对象与用户信息。

    返回 (authenticator, name, username)。
    """
    credentials, cfg = load_credentials()

    if not credentials["usernames"]:
        _render_setup_help()
        st.stop()

    cookie_name = cfg.get("cookie_name", "music_personality_app")
    cookie_key = cfg.get("cookie_key")
    if not cookie_key:
        st.error("secrets 中缺少 auth.cookie_key，请参考 .streamlit/secrets.toml.example 配置。")
        st.stop()

    authenticator = stauth.Authenticate(
        credentials,
        cookie_name=cookie_name,
        cookie_key=cookie_key,
        cookie_expiry_days=float(cfg.get("cookie_expiry_days", 7)),
        auto_hash=True,  # 明文自动哈希；已是 bcrypt 哈希的（注册用户）会原样保留
    )

    # 已认证（本会话登录过）则不再渲染登录界面，直接进入仪表盘；
    # Cookie 免登录的首次访问仍会先显示一次登录壳，点任意交互后即消失
    already = st.session_state.get("authentication_status") is True

    if not already:
        st.title("🎧 性格 × 流行歌手推荐器")
        st.caption("请登录后使用。首次使用请切换到「注册」标签创建账号。")

        tab_login, tab_register = st.tabs(["登录", "注册"])

        with tab_login:
            authenticator.login(location="main", fields=LOGIN_FIELDS, clear_on_submit=False)

        with tab_register:
            st.caption(PASSWORD_HINT_CN)
            try:
                result = authenticator.register_user(
                    location="main", captcha=True, fields=REGISTER_FIELDS
                )
                # register_user 成功时返回 (email, username, name)
                if result and result[1]:
                    _persist_new_user(authenticator, result[1])
                    st.success(f"账号「{result[1]}」注册成功，请切换到「登录」标签登录。")
                    st.balloons()
            except Exception as exc:  # noqa: BLE001 - 库会抛各类校验异常，原样提示给用户
                st.error(str(exc))

        status = st.session_state.get("authentication_status")
        if status is False:
            st.error("用户名或密码错误")
        elif status is None:
            st.info("请输入用户名和密码，或先注册一个账号")

    if not st.session_state.get("authentication_status"):
        st.stop()

    return authenticator, st.session_state.get("name"), st.session_state.get("username")


def _credentials_of(authenticator: stauth.Authenticate) -> dict:
    """取到 Authenticate 内部那份内存凭据字典。

    注意：Authenticate 视图对象本身不暴露 credentials，它藏在
    controller -> model 里面。这里做多路径兜底，避免库升级改内部结构后直接崩。
    """
    for path in (
        lambda a: a.authentication_controller.authentication_model.credentials,
        lambda a: a.authentication_model.credentials,
        lambda a: a.credentials,
    ):
        try:
            creds = path(authenticator)
            if isinstance(creds, dict) and "usernames" in creds:
                return creds
        except AttributeError:
            continue
    return {}


def _persist_new_user(authenticator: stauth.Authenticate, username: str) -> None:
    """把刚注册的用户从内存凭据写入 data/users.json（密码已是 bcrypt 哈希）。"""
    entry = _credentials_of(authenticator).get("usernames", {}).get(username)
    if not entry:
        return
    registered = _load_registered()
    registered[username] = {
        "email": entry.get("email"),
        "first_name": entry.get("first_name"),
        "last_name": entry.get("last_name"),
        "password": entry.get("password"),  # bcrypt 哈希，非明文
        "roles": entry.get("roles"),
    }
    if entry.get("password_hint"):
        registered[username]["password_hint"] = entry["password_hint"]
    _save_registered(registered)


def _render_setup_help() -> None:
    """没有任何账号可用时的配置指引页（避免应用直接崩掉）。"""
    st.title("🎧 性格 × 流行歌手推荐器")
    st.error("尚未配置任何登录账号，无法进入应用。")
    st.markdown(
        """
### 本地配置

在项目根目录创建 `.streamlit/secrets.toml`（该文件已被 .gitignore 排除，不会进仓库）：

```toml
[auth]
cookie_name = "music_personality_app"
cookie_key = "随便一串足够长的随机字符串"
cookie_expiry_days = 7

[auth.usernames.admin]
email = "you@example.com"
first_name = "Admin"
last_name = "User"
password = "你的密码"
```

### 线上部署配置

在 Streamlit Community Cloud 的 App 页面 →
**Settings → Secrets** 里粘贴同样的内容（不要提交到仓库）。

> 密码要求：8~20 位，含大小写字母、数字、特殊字符。
> 也可直接填 bcrypt 哈希值（以 `$2b$` 开头），程序会自动识别、不会重复哈希。
"""
    )

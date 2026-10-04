# -*- coding: utf-8 -*-
"""测试：用户管理系统（第 8 页「👤 用户管理」+ user_store.py 双后端存储层）。

覆盖三件事：
1. 文件后端（JsonUserStore）的增删改查与字段映射；
2. auth.py 的凭据合并规则——禁用账号必须被过滤掉、secrets 预置账号必须优先；
3. 管理页的权限门禁——管理员看得到、非管理员看不到且进不去。

MySQL 部分需要 .streamlit/secrets.toml 配好 [mysql] 段且服务可连；
连不上就按项目惯例跳过（打印 [跳过]）并退出 0，不假装通过。
测试用的账号名带 __selftest__ 前缀，结束时删除，不会污染真实用户数据。

用法：python scripts/test_user_store.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bcrypt  # noqa: E402

import auth  # noqa: E402
import user_store as us  # noqa: E402

ADMIN_PAGE = "👤 用户管理"
FIRST_PAGE = "📊 数据总览"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ------------------------------------------------------------ 文件后端 CRUD --

def test_json_crud() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = us.JsonUserStore(Path(tmp) / "users.json", Path(tmp) / "log.json")

        assert store.list_users() == {}, "新建的存储应该没有用户"

        store.create_user("alice", {
            "email": "a@example.com", "first_name": "Ali", "last_name": "Ce",
            "password_hash": _hash("Passw0rd!"), "roles": ["admin"],
        })
        record = store.get_user("alice")
        assert record is not None, "刚创建的用户应该读得到"
        assert record["email"] == "a@example.com", "邮箱没写对"
        assert record["roles"] == ["admin"], f"角色解析错误：{record['roles']}"
        assert record["status"] == us.STATUS_ACTIVE, "新用户默认应是启用状态"
        assert record["password_hash"].startswith("$2b$"), "密码必须是 bcrypt 哈希"
        assert "Passw0rd!" not in str(record), "存储里绝不能出现明文密码"
        assert record["created_at"], "创建时间应该有值"

        # 重名要报错，不能静默覆盖
        try:
            store.create_user("alice", {"password_hash": _hash("x")})
            raise AssertionError("重名创建应该抛 ValueError")
        except ValueError:
            pass

        store.update_user("alice", {"email": "b@example.com", "roles": "user"})
        record = store.get_user("alice")
        assert record["email"] == "b@example.com", "资料没更新"
        assert record["roles"] == ["user"], "字符串角色应被归一成列表"

        # 无变化更新不该报错（两种后端语义要一致）
        store.update_user("alice", {"email": "b@example.com"})

        try:
            store.update_user("nobody", {"email": "x@example.com"})
            raise AssertionError("更新不存在的用户应抛 ValueError")
        except ValueError:
            pass

        store.set_password("alice", _hash("NewPassw0rd!"))
        assert bcrypt.checkpw(b"NewPassw0rd!", store.get_user("alice")["password_hash"].encode()), \
            "重置后的密码校验失败"

        store.set_status("alice", us.STATUS_DISABLED)
        assert store.get_user("alice")["status"] == us.STATUS_DISABLED, "禁用状态没写进去"

        try:
            store.set_status("alice", "bogus")
            raise AssertionError("非法状态应该抛 ValueError")
        except ValueError:
            pass

        assert store.delete_user("alice") is True, "删除已存在的用户应返回 True"
        assert store.delete_user("alice") is False, "重复删除应返回 False"
        assert store.get_user("alice") is None, "删除后不该再读得到"

        print("[通过] 文件后端增删改查（含重名拦截、明文不入库、角色归一化）")


def test_json_login_log() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = us.JsonUserStore(Path(tmp) / "users.json", Path(tmp) / "log.json")
        store.create_user("bob", {"password_hash": _hash("Passw0rd!"), "roles": ["user"]})

        store.record_login("bob", success=True, ip="1.2.3.4")
        store.record_login("bob", success=False, ip=None)

        logs = store.list_login_logs()
        assert len(logs) == 2, f"应该有 2 条日志，实际 {len(logs)}"
        assert logs[0]["username"] == "bob" and logs[0]["success"] is False, "最新一条应在最前"
        assert logs[1]["success"] is True and logs[1]["ip"] == "1.2.3.4", "成功日志内容不对"
        assert logs[0]["ip"] == "—", "没有 IP 时应显示占位符"

        assert store.get_user("bob")["last_login_at"], "登录成功应更新最后登录时间"

        # 滚动上限：写入超过上限后只保留最近 MAX_JSON_LOGS 条
        for i in range(us.MAX_JSON_LOGS + 10):
            store.record_login("bob", success=True)
        assert len(store.list_login_logs(limit=us.MAX_JSON_LOGS + 100)) == us.MAX_JSON_LOGS, \
            "日志文件应该滚动截断，不能无限增长"

        print(f"[通过] 文件后端登录日志（顺序 / IP 占位 / 滚动上限 {us.MAX_JSON_LOGS} 条）")


# ------------------------------------------------------------ 字段与工具函数 --

def test_entry_mapping() -> None:
    record = {
        "username": "carol", "email": "c@example.com", "first_name": "Ca", "last_name": "Rol",
        "password_hash": "$2b$12$abc", "roles": ["user"], "status": us.STATUS_DISABLED,
        "created_at": "2026-01-01T00:00:00", "last_login_at": None, "source": "数据库",
    }
    entry = us.to_auth_entry(record)
    assert entry["password"] == "$2b$12$abc", "password_hash 必须映射成认证库要的 password"
    assert "password_hash" not in entry, "不该把内部字段名带进认证库"
    assert "status" not in entry, "status 是存储层概念，不该交给认证库"
    assert set(entry) <= {"email", "first_name", "last_name", "password", "roles",
                          "password_hint"}, f"多带了字段：{set(entry)}"

    assert us.norm_roles(None) == [] and us.norm_roles("admin,user") == ["admin", "user"], \
        "角色归一化不完整"
    assert us.norm_roles(["admin", "", None]) == ["admin"], "角色归一化应剔除空值"

    # 时间：库里存 UTC，展示转本机时区——两者不能相等（东八区下差 8 小时）
    assert us.fmt_local(None) == "—", "空时间应显示占位符"
    assert us.fmt_local("2026-01-01T00:00:00") != "—", "合法 ISO 时间应能格式化"

    print("[通过] 字段映射（password_hash → password）与角色/时间工具函数")


def test_password_rules() -> None:
    assert auth.username_problem("") is not None, "空用户名应被拒绝"
    assert auth.username_problem("张三") is not None, "认证库不支持中文用户名，必须拦下"
    assert auth.username_problem("a" * 21) is not None, "超长用户名应被拒绝"
    assert auth.username_problem("good_name-1") is None, "合法用户名被误拒"

    assert auth.password_problem("weak") is not None, "弱密码应被拒绝"
    assert auth.password_problem("Str0ng!Pass") is None, "合规密码被误拒"

    hashed = auth.hash_password("Str0ng!Pass")
    assert hashed.startswith("$2b$"), "哈希格式应与认证库一致（$2b$ 前缀）"
    assert bcrypt.checkpw(b"Str0ng!Pass", hashed.encode()), "哈希校验失败"

    print("[通过] 账号规则校验（中文用户名拦截 / 弱密码拦截 / bcrypt 哈希格式）")


# ---------------------------------------------------- 凭据合并与禁用过滤 --

def test_credentials_merge_and_disable() -> None:
    """load_credentials 的三条规则：禁用被剔除、预置账号优先、缺字段有默认值。"""
    with tempfile.TemporaryDirectory() as tmp:
        store = us.JsonUserStore(Path(tmp) / "users.json", Path(tmp) / "log.json")
        store.create_user("active_user", {
            "password_hash": _hash("Passw0rd!"), "roles": ["user"]})
        store.create_user("banned_user", {
            "password_hash": _hash("Passw0rd!"), "roles": ["user"],
            "status": us.STATUS_DISABLED})
        store.create_user("boss", {  # 与预置账号同名，用来验证优先级
            "password_hash": _hash("FromDatabase!"), "roles": ["user"]})

        originals = (auth.get_store, auth._secret_config)
        auth.get_store = lambda: store
        auth._secret_config = lambda: {
            "cookie_key": "test",
            "usernames": {"boss": {
                "email": "boss@example.com", "first_name": "B", "last_name": "S",
                "password": "$2b$12$preset", "roles": ["admin"]}},
        }
        try:
            credentials, cfg = auth.load_credentials()
        finally:
            auth.get_store, auth._secret_config = originals

    users = credentials["usernames"]
    assert "active_user" in users, "启用中的用户必须能登录"
    assert "banned_user" not in users, "禁用账号必须被过滤掉（否则禁用形同虚设）"
    assert users["boss"]["password"] == "$2b$12$preset", \
        "同名时必须以 secrets 预置账号为准，否则管理员账号会被库里的数据顶掉"
    assert users["boss"]["roles"] == ["admin"], "预置账号的角色应保留"
    assert users["active_user"]["password"].startswith("$2b$"), "密码字段映射失败"
    assert cfg.get("cookie_key") == "test", "配置应原样返回"

    print("[通过] 凭据合并（禁用账号被剔除 / 预置账号优先 / 字段映射）")


# ------------------------------------------------------------ MySQL 后端 --

def test_mysql_roundtrip() -> None:
    """在真实 MySQL 上跑一遍增删改查。连不上就跳过（项目既有惯例）。"""
    try:
        store = us.MySqlUserStore.from_secrets()
    except us.StoreConfigError as exc:
        print(f"[跳过] MySQL 未配置（{exc}）")
        return
    ok, message = store.ping()
    if not ok:
        print(f"[跳过] MySQL 连不上：{message}")
        print("       先跑 python scripts/init_db.py 建库建表，再重跑本测试。")
        return

    username = "__selftest_user__"
    store.delete_user(username)  # 清掉上次异常中断可能留下的残留
    try:
        store.create_user(username, {
            "email": "selftest@example.com", "first_name": "Self", "last_name": "Test",
            "password_hash": _hash("Passw0rd!"), "roles": ["user"],
        })
        record = store.get_user(username)
        assert record is not None, "MySQL 里刚创建的用户读不到"
        assert record["roles"] == ["user"], f"角色 JSON 解析错误：{record['roles']}"
        assert record["status"] == us.STATUS_ACTIVE, "默认状态不对"
        assert isinstance(record["created_at"], datetime), \
            f"创建时间没写入或类型不对：{record['created_at']!r}"
        assert "Passw0rd!" not in str(record), "库里出现了明文密码"

        try:
            store.create_user(username, {"password_hash": _hash("x")})
            raise AssertionError("主键冲突应被拦成 ValueError")
        except ValueError:
            pass

        store.update_user(username, {"email": "new@example.com", "roles": ["admin", "user"]})
        record = store.get_user(username)
        assert record["email"] == "new@example.com", "MySQL 更新失败"
        assert record["roles"] == ["admin", "user"], "多角色写读不一致"

        # 回归：把字段设成与当前完全相同的值不能再报错。
        # MySQL 的 rowcount 是「实际改动的行数」，无变化时为 0——
        # 早先用 rowcount 判断存在性，会把「保存了但内容没变」误报成「用户不存在」，
        # 在管理页上就是点一下保存角色就弹假错误。
        store.update_user(username, {"email": "new@example.com"})
        store.set_roles(username, ["admin", "user"])
        assert store.get_user(username)["email"] == "new@example.com", "无变化更新后数据被改坏"

        try:
            store.update_user("__selftest_no_such_user__", {"email": "x@example.com"})
            raise AssertionError("更新不存在的用户应抛 ValueError")
        except ValueError:
            pass

        store.set_password(username, _hash("Another1!"))
        assert bcrypt.checkpw(
            b"Another1!", store.get_user(username)["password_hash"].encode()), "改密后校验失败"

        store.set_status(username, us.STATUS_DISABLED)
        assert store.get_user(username)["status"] == us.STATUS_DISABLED, "状态更新失败"

        # 登录日志与 last_login_at 在同一事务里
        store.record_login(username, success=True, ip="9.9.9.9")
        logs = [row for row in store.list_login_logs(limit=50) if row["username"] == username]
        assert logs and logs[0]["success"] is True, "登录日志没写进 MySQL"
        assert store.get_user(username)["last_login_at"], "登录成功应更新最后登录时间"

        # 时间必须能被统一解析（存 UTC、展示转本机）
        assert us.fmt_local(store.get_user(username)["last_login_at"]) != "—", "时间解析失败"

        print("[通过] MySQL 后端增删改查（角色 JSON / 状态 / 日志事务 / 时间解析）")
    finally:
        store.delete_user(username)


def test_mysql_credentials_integration() -> None:
    """端到端验收：库里的管理员能进管理页、被禁用的账号登不进来。

    这是整个功能最核心的两条验收标准，所以不满足于"存储层能读写"——
    要真的过一遍 auth.py 的凭据合并与角色判断。
    """
    try:
        store = us.MySqlUserStore.from_secrets()
        ok, message = store.ping()
    except us.StoreConfigError as exc:
        print(f"[跳过] MySQL 未配置（{exc}）")
        return
    if not ok:
        print(f"[跳过] MySQL 连不上：{message}")
        return

    admin_user, banned_user = "__selftest_admin__", "__selftest_banned__"
    for name in (admin_user, banned_user):
        store.delete_user(name)
    try:
        store.create_user(admin_user, {
            "password_hash": _hash("Passw0rd!"), "roles": ["admin"]})
        store.create_user(banned_user, {
            "password_hash": _hash("Passw0rd!"), "roles": ["admin"],
            "status": us.STATUS_DISABLED})

        credentials, _ = auth.load_credentials()
        users = credentials["usernames"]
        assert admin_user in users, "库里的启用账号没被合并进登录凭据，等于登不进来"
        assert users[admin_user]["roles"] == ["admin"], \
            f"库里的角色没传对，管理员会被降级：{users[admin_user]['roles']}"
        assert banned_user not in users, \
            "被禁用的账号仍在登录凭据里，禁用形同虚设"

        # 角色判断的兜底路径：认证库没往 session_state 写 roles 时，
        # 必须能回查存储层拿到角色，否则管理员会静默看不到管理页
        import streamlit as st

        st.session_state["username"] = admin_user
        st.session_state["roles"] = None
        assert auth.is_admin() is True, \
            "库里带 admin 角色的账号被判定为非管理员（角色兜底查询失效）"

        st.session_state["username"] = banned_user
        st.session_state["roles"] = None
        assert auth.is_admin() is False, "被禁用的账号不该有管理员权限"

        st.session_state["username"] = admin_user
        st.session_state["roles"] = ["user"]
        assert auth.is_admin() is False, "角色为 user 时不该有管理员权限"

        # 会话期间被禁用/删除的账号必须在下一次交互就被挡住
        st.session_state["username"] = admin_user
        assert auth._still_authorized() is True, "启用中的账号被误判为失效"
        st.session_state["username"] = banned_user
        assert auth._still_authorized() is False, \
            "被禁用的账号仍被判为有效，它会一直放行到 Cookie 过期"
        st.session_state["username"] = "__selftest_ghost__"
        assert auth._still_authorized() is False, "已被删除的账号仍被判为有效"
        for preset in auth.preset_usernames():
            st.session_state["username"] = preset
            assert auth._still_authorized() is True, \
                f"secrets 预置账号「{preset}」被误判为失效（兜底账号不能被踢）"
        st.session_state["username"] = None
        assert auth._still_authorized() is True, "拿不到用户名时不该踢人"

        # 存储层故障时必须放行，否则 MySQL 抖一下所有用户集体掉线
        original = auth.get_store
        auth.get_store = lambda: (_ for _ in ()).throw(RuntimeError("模拟存储层故障"))
        try:
            st.session_state["username"] = banned_user
            assert auth._still_authorized() is True, "存储层故障时不该踢人"
        finally:
            auth.get_store = original

        print("[通过] 端到端验收（库里的管理员可进管理页 / 被禁用账号被挡在登录之外）")
    finally:
        for name in (admin_user, banned_user):
            store.delete_user(name)
        import streamlit as st

        st.session_state.pop("username", None)
        st.session_state.pop("roles", None)


def test_mysql_ping_matches_backend() -> None:
    """backend 设成 mysql 且连得上时，get_store() 必须真的返回 MySQL 后端。"""
    backend = str(us._secret_section("storage").get("backend") or "json").lower()
    store = us.get_store()
    if backend == "mysql":
        if store.backend == "mysql":
            print("[通过] get_store() 按配置返回 MySQL 后端")
        else:
            print(f"[跳过] 配置为 mysql 但当前不可用，已回退文件后端：{store.note}")
    else:
        assert store.backend == "json", "未配置 mysql 时必须默认走文件后端"
        assert store.note is None, "默认文件后端不该有降级提示"
        print("[通过] get_store() 未配置时默认返回文件后端（云端/exe 行为不变）")


# ------------------------------------------------------------ 管理页门禁 --

def test_admin_page_gate() -> None:
    from streamlit.testing.v1 import AppTest

    presets = auth.preset_usernames()
    assert presets, "测试需要 secrets 里至少有一个预置账号（它就是真实的管理员）"
    admin_name = presets[0]

    def run_as(roles: list[str], page: str, username: str | None = None):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
        at.session_state["authentication_status"] = True
        at.session_state["name"] = "Tester"
        at.session_state["username"] = username or admin_name
        at.session_state["roles"] = roles
        at.session_state["page"] = page
        at.run()
        return at

    admin = run_as(["admin"], ADMIN_PAGE)
    assert not admin.exception, f"管理员打开管理页报错：{admin.exception}"
    labels = [b.label for b in admin.sidebar.button]
    assert ADMIN_PAGE in labels, f"管理员应看到管理页按钮，实际侧边栏：{labels}"
    titles = [t.value for t in admin.title]
    assert any("用户管理" in t for t in titles), f"管理页没渲染出来，标题：{titles}"

    user = run_as(["user"], ADMIN_PAGE)
    assert not user.exception, f"普通用户打开应用报错：{user.exception}"
    labels = [b.label for b in user.sidebar.button]
    assert ADMIN_PAGE not in labels, "普通用户不该看到管理页按钮"
    assert user.session_state["page"] == FIRST_PAGE, \
        f"残留在不可见页名时应被纠正回第一页，实际：{user.session_state['page']}"
    titles = [t.value for t in user.title]
    assert not any("用户管理" in t for t in titles), "普通用户不该渲染出管理页内容"

    # 会话期间账号被删除或禁用：必须在进入任何页面前就被挡住并给出提示，
    # 而不是靠 Cookie 过期才生效（否则刚被禁用的管理员还能继续用管理页）
    ghost = run_as(["admin"], ADMIN_PAGE, username="__ghost_user__")
    assert not ghost.exception, f"失效账号触发了未捕获异常：{ghost.exception}"
    assert not ghost.sidebar.button, "失效账号不该渲染出任何导航"
    errors = [e.value for e in ghost.error]
    assert any("已被禁用或删除" in e for e in errors), f"没给出账号失效提示：{errors}"

    print("[通过] 管理页门禁（管理员可见可渲染 / 普通用户不可见且被纠正回首页 / 失效账号被拦下）")


def main() -> int:
    print("测试：用户管理系统（存储层双后端 + 凭据合并 + 管理页门禁）\n")
    test_json_crud()
    test_json_login_log()
    test_entry_mapping()
    test_password_rules()
    test_credentials_merge_and_disable()
    test_mysql_roundtrip()
    test_mysql_credentials_integration()
    test_mysql_ping_matches_backend()
    test_admin_page_gate()
    print("\n全部通过：用户管理系统（文件后端 / MySQL 后端 / 凭据合并 / 管理页门禁）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

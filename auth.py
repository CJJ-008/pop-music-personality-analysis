# -*- coding: utf-8 -*-
"""登录认证模块：登录门禁 + 角色判断 + 登录日志。

安全设计（这几点是刻意的，不是随手写的）：
1. **凭据绝不写进代码**：预置账号放在 st.secrets——本地是 .streamlit/secrets.toml，
   线上在 Streamlit Cloud 面板配置。因为本仓库是公开的，把密码写进 app.py 等于
   把密码发布到全网（还会被 GitHub 的密钥扫描机器人抓到）。
2. **密码只存 bcrypt 哈希**：注册时由 streamlit-authenticator 哈希，落盘的是哈希值，
   任何地方都不保存明文。
3. **注册用户必须自己落盘**：streamlit-authenticator 的 register_user 只更新内存里的
   凭据字典、不写文件，而 Streamlit 每次交互都会重跑脚本、重建 Authenticate 对象，
   不落盘的话用户注册完一刷新就没了。落盘动作交给 user_store.py——
   本地可走 MySQL，云端/exe 走 data/users.json（见该模块开头的场景说明）。
4. **持久化能力的真实边界**：本地跑（配了 [mysql] 后端）时注册账号进数据库，
   重启不丢；Streamlit Community Cloud 上拿不到你本机的 MySQL，仍走文件存储，
   而云端文件系统是临时的，应用重启或重新部署后注册账号依旧会丢
   （secrets 预置账号不受影响）。这个差别不能含糊其辞。

分层：本模块负责「登录/加密/角色」这些认证逻辑，
用户数据从哪来、往哪写由 user_store.py 负责，两者通过统一接口对接。
"""
from __future__ import annotations

import re
from collections.abc import Mapping

import streamlit as st
import streamlit_authenticator as stauth

# resolve_dirs 的实现在 user_store.py（「可写数据文件放哪」属于存储层的事），
# 这里转出来是为了让 `from auth import resolve_dirs` 的既有写法继续可用（app.py 在用）。
from user_store import (
    ROLE_ADMIN,
    STATUS_ACTIVE,
    STATUS_DISABLED,
    get_store,
    norm_roles,
    resolve_dirs,
    to_auth_entry,
)
import theme

# 管理员角色名只在 user_store.py 定义一次（角色下拉、写计划也都用它），
# 这里引用而不是再写一遍字面量——两处各写一个 "admin"，迟早有人只改一处。
# 权限认角色不认「用户名等于 admin」这种约定：用户名可以随便起，角色才是授权。
ADMIN_ROLE = ROLE_ADMIN

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


def _set_note(message: str | None) -> None:
    """把「存储层降级了」这类提示记进 session_state，供页面显示。

    不用 st.warning 直接弹，是因为 load_credentials() 在登录前就会被调用，
    那时页面还没开始渲染；记下来让页面自己决定显示在哪。
    """
    if not message:
        return
    try:
        st.session_state["_store_note"] = message
    except Exception:  # noqa: BLE001 - 非 Streamlit 环境（脚本/测试）下忽略
        pass


def storage_note() -> str | None:
    """存储层降级说明（例如 MySQL 连不上、已回退到文件），没有则返回 None。"""
    try:
        return st.session_state.get("_store_note")
    except Exception:  # noqa: BLE001
        return None


def load_credentials() -> tuple[dict, dict]:
    """合并「secrets 预置账号」与「存储层里的用户」，返回 (凭据, 配置)。

    同名时以 secrets 预置账号为准，避免库里的用户覆盖管理员账号。
    这条优先级是刻意的兜底：即使 MySQL 挂了、密码填错了，你依然能用
    secrets 里的管理员账号登进来修。

    已禁用的账号在这里就被剔除——认证库根本拿不到它，等于它不存在，
    于是自然登不进来。这样实现「启用/禁用」不必去改认证库的内部逻辑。
    """
    cfg = _secret_config()
    base = dict(cfg.get("usernames", {}) or {})

    registered: dict = {}
    try:
        store = get_store()
        for username, record in store.list_users().items():
            if record.get("status") == STATUS_DISABLED:
                continue
            registered[username] = to_auth_entry(record)
        _set_note(getattr(store, "note", None))
    except Exception as exc:  # noqa: BLE001
        # 存储层故障不该让登录页整个崩掉——最坏情况退回「只有预置账号可登录」
        _set_note(f"读取用户存储失败（{exc}），本次仅加载 secrets 预置账号。")

    registered.update(base)  # 预置账号优先
    return {"usernames": registered}, cfg


# ===== 登录页视觉（D34）：居中窄卡片 + 深色氛围光晕 =====
# 只在未登录分支注入，登录成功 rerun 后自然消失，主应用不受影响。
# CSS 走 st.html（样式能生效、脚本不执行——app.py 的 D22/D30 已验证过这一结论）；
# 表单控件由 streamlit-authenticator 库内部渲染，本项目只能整体包裹 + CSS 定位，
# 不能逐个替换控件，所以这里全是针对 Streamlit DOM 的样式覆盖。
# 登录页配色跟随当前主题（D35）：字段来自 theme.py 的预设，
# 默认主题「霓虹夜曲」下与 D34 当时的效果完全一致。
_LOGIN_CSS_TMPL = """<style>
/* 页面收窄居中：告别全宽表单。
   注意要把左右大内边距一并压掉：容器 430px 减去默认左右各 80px 内边距后
   内容区只剩 270px，卡片会跟着缩（浏览器实测踩过这个坑） */
[data-testid="stMainBlockContainer"] {
    max-width: 430px;
    margin: 0 auto;
    padding-top: max(6vh, 40px) !important;
    padding-left: 18px !important;
    padding-right: 18px !important;
}

/* 深色氛围光晕：颜色随主题（theme.py）；顶栏透明让渐变透出来 */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(1100px 520px at 12% -10%, __GLOW_A__, transparent 60%),
        radial-gradient(950px 520px at 90% 110%, __GLOW_B__, transparent 60%),
        __PAGE__ !important;
}
[data-testid="stHeader"] { background: transparent !important; }

/* 头部：圆形徽章 + 小号标题 + 灰色副标题 */
.login-hero { text-align: center; margin: 2px 0 14px; }
.login-hero .hero-badge {
    width: 56px; height: 56px; margin: 0 auto 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 26px; line-height: 1; border-radius: 50%;
    background: linear-gradient(135deg, __GLOW_A__, __GLOW_B__);
    border: 1px solid __ACCENT_SOFT__;
    box-shadow: 0 6px 22px __ACCENT_SOFT__;
}
.login-hero h1 {
    margin: 0 0 6px; font-size: 1.3rem; font-weight: 700;
    letter-spacing: .5px; color: #f5f5f5;
}
.login-hero p { margin: 0; font-size: .86rem; color: rgba(245, 245, 245, .6); }

/* 主内容纵向块拉满容器：实测 1.64 的纵向块默认收缩包裹（fit-content），
   不拉满的话卡片、输入框会全部缩成内容宽 */
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { width: 100% !important; }

/* 登录/注册 tabs 整体卡片化：深色面板 + 细边框 + 柔和投影 */
[data-testid="stTabs"] {
    width: 100% !important;
    background: __SIDEBAR__ !important;
    border: 1px solid rgba(255, 255, 255, .08);
    border-radius: 16px;
    padding: 14px 18px 16px;
    box-shadow: 0 12px 36px rgba(0, 0, 0, .42);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] { justify-content: center; gap: 40px; }
/* 卡片内不再套一层表单边框，保持单张卡片的干净观感 */
[data-testid="stForm"] { border: none; padding: 2px 0 0; }

/* 输入框盒子：1.64 的文本框是 react-aria 结构（旧的 [data-baseweb="input"] 已不存在），
   盒子底色与卡片同为 #161b26 且边框同色会"隐形"，改成深一档底色 + 可见描边，聚焦描红 */
[data-testid="stTextInput"] .react-aria-TextField > div {
    background: __PAGE__ !important;
    border: 1px solid rgba(255, 255, 255, .14) !important;
    border-radius: 10px;
}
[data-testid="stTextInput"] .react-aria-TextField:focus-within > div {
    border-color: __ACCENT__ !important;
}

/* 提交按钮拉通卡片宽度：1.64 的元素容器默认内容宽，要把整条祖先链都拉满。
   Streamlit 自带样式选择器优先级更高，宽度/背景覆盖必须 !important（浏览器实测验证过） */
[data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]) { width: 100% !important; }
[data-testid="stForm"] [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]) > div { width: 100% !important; }
[data-testid="stFormSubmitButton"] { width: 100% !important; }
[data-testid="stFormSubmitButton"] button { width: 100% !important; border-radius: 10px; }
/* 库的提交按钮是 secondary 灰样式，染成主色让登录/注册按钮成为卡片视觉焦点 */
[data-testid="stBaseButton-secondaryFormSubmit"] {
    background: __ACCENT__ !important;
    border-color: __ACCENT__ !important;
    color: rgb(255, 255, 255) !important;
}
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    background: __ACCENT_HOVER__ !important;
    border-color: __ACCENT_HOVER__ !important;
    color: rgb(255, 255, 255) !important;
}
[data-testid="stBaseButton-secondaryFormSubmit"]:focus-visible {
    outline-color: rgb(255, 255, 255) !important;
}
/* tab 已标明「登录/注册」，隐藏表单内部重复的小标题 */
[data-testid="stTabs"] [data-testid="stForm"] h3 { display: none; }

/* 卡片下方的提示条贴紧一点 */
[data-testid="stAlert"] { margin-top: 14px; }
</style>"""


def _login_css() -> str:
    """按当前主题渲染登录页 CSS（D35）。

    用 __TOKEN__ 替换而不是 str.format()：模板里全是 CSS 字面大括号，
    format 会把它们误当占位符（首次实现就栽在这个 KeyError 上）。
    """
    p = theme.current_preset()
    return (
        _LOGIN_CSS_TMPL
        .replace("__ACCENT_HOVER__", p["accent_hover"])
        .replace("__ACCENT_SOFT__", p["accent_soft"])
        .replace("__ACCENT__", p["accent"])
        .replace("__PAGE__", p["page"])
        .replace("__SIDEBAR__", p["sidebar"])
        .replace("__GLOW_A__", p["glow_a"])
        .replace("__GLOW_B__", p["glow_b"])
    )

_LOGIN_HEADER = """
<div class="login-hero">
  <div class="hero-badge">🎧</div>
  <h1>性格 × 流行歌手推荐器</h1>
  <p>请登录后使用 · 首次使用请切换到「注册」创建账号</p>
</div>
"""


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
        st.html(_login_css())
        st.markdown(_LOGIN_HEADER, unsafe_allow_html=True)

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
            _log_attempt(authenticator, success=False)
        elif status is None:
            st.info("请输入用户名和密码，或先注册一个账号")
        elif status is True:
            # 能走到这里说明本次运行刚完成认证（表单登录成功，或 Cookie 免登录），
            # 记一条「会话开始」；下一次重跑 already 为 True，不会再记一遍。
            _log_attempt(authenticator, success=True)

        note = storage_note()
        if note:
            st.warning(note)

    if not st.session_state.get("authentication_status"):
        st.stop()

    # 已登录的账号可能在本会话期间被禁用或删除。cookie 那条路会自动拦住
    # （认证库发现用户名不在名单里就拒绝），但本会话的 authentication_status
    # 仍是 True，会一直放行到 Cookie 过期。这里主动核对，让禁用立刻生效。
    if not _still_authorized():
        for key in ("authentication_status", "name", "username", "email", "roles"):
            st.session_state[key] = None
        st.error("该账号已被禁用或删除，请重新登录；如果是误操作，请联系管理员。")
        st.stop()

    # 登录成功的那一次运行里 already 仍是 False，登录界面已经渲染在页面上了。
    # 触发一次重跑，让下一次运行走 already=True 分支，只显示仪表盘，
    # 避免登录表单与仪表盘短暂同屏。
    if not already:
        st.rerun()

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
    """把刚注册的用户从内存凭据写进存储层（密码已是 bcrypt 哈希）。

    必须自己写：认证库的 register_user 只更新内存字典、不落盘，
    而 Streamlit 每次交互都会重跑脚本、重建 Authenticate 对象。
    """
    entry = _credentials_of(authenticator).get("usernames", {}).get(username)
    if not entry:
        return
    record = {
        "email": entry.get("email"),
        "first_name": entry.get("first_name"),
        "last_name": entry.get("last_name"),
        "password_hash": entry.get("password"),  # bcrypt 哈希，非明文
        # 自助注册的账号一律给普通角色，管理员只能由管理员在管理页授予
        "roles": entry.get("roles") or ["user"],
        "status": STATUS_ACTIVE,
    }
    if entry.get("password_hint"):
        record["password_hint"] = entry["password_hint"]
    get_store().create_user(username, record)


def _attempted_username(authenticator: stauth.Authenticate) -> str:
    """尽力还原登录失败时输入的用户名。

    认证库失败时不写 st.session_state['username']（只把 authentication_status 置 False），
    但它会给「账号确实存在、只是密码错」的那种情况递增 failed_login_attempts 计数器，
    而凭据字典每次运行都由 load_credentials() 重建（计数器不会跨次残留），
    所以「计数 > 0 的那个账号」就是刚被尝试的账号。

    用户名压根不存在时（含已被禁用的账号——它在 load_credentials 里就被剔掉了）
    没有任何痕迹可循，只能如实记成「未知用户」，不猜。
    """
    best, best_count = "", 0
    for username, entry in _credentials_of(authenticator).get("usernames", {}).items():
        count = entry.get("failed_login_attempts") or 0
        if count > best_count:
            best, best_count = username, count
    return best


def _client_ip() -> str | None:
    """尽力取客户端 IP；取不到就如实返回 None，不编造。

    本地直连时 Streamlit 不暴露来源地址；部署在 Streamlit Cloud 或反向代理后面时，
    真实地址在 X-Forwarded-For 的第一个值里。
    """
    try:
        headers = st.context.headers
    except Exception:  # noqa: BLE001 - 老版本或非 Streamlit 环境
        return None
    forwarded = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return None


def _log_attempt(authenticator: stauth.Authenticate, success: bool) -> None:
    """记一条登录日志。

    日志是附加能力，写失败不该挡住登录本身，所以整段兜异常；
    但也不静默吞掉——把原因记进提示，让人知道日志漏了。
    """
    try:
        if success:
            username = st.session_state.get("username") or ""
        else:
            username = _attempted_username(authenticator)
        get_store().record_login(username or "（未知用户）", success=success, ip=_client_ip())
    except Exception as exc:  # noqa: BLE001
        _set_note(f"登录日志写入失败（{exc}）。")


def current_roles() -> list[str]:
    """当前登录用户的角色列表。

    认证库登录成功时会写 st.session_state['roles']，优先用它；取不到则依次回退到
    「按用户名查存储层」和「查 secrets 预置账号」。做这些回退是因为：
    权限判断一旦静默失效，后果是管理员看不到管理页、且没有任何报错可查——
    那比报错难排查得多。
    """
    roles = st.session_state.get("roles")
    if roles:
        return norm_roles(roles)

    username = st.session_state.get("username")
    if not username:
        return []

    try:
        record = get_store().get_user(username)
        # 被禁用的账号不算数：它已经登不进来了，更不该因为库里还留着
        # roles = ["admin"] 就继续被当成管理员
        if record and record.get("status") != STATUS_DISABLED:
            return norm_roles(record.get("roles"))
    except Exception:  # noqa: BLE001 - 存储层故障时继续往下回退
        pass

    try:
        credentials, _ = load_credentials()
        entry = credentials.get("usernames", {}).get(username)
        if entry:
            return norm_roles(entry.get("roles"))
    except Exception:  # noqa: BLE001
        pass
    return []


def is_admin() -> bool:
    """是否有管理员角色。侧边栏是否显示管理页、管理页是否渲染，都以它为准。"""
    return ADMIN_ROLE in current_roles()


def _still_authorized() -> bool:
    """本会话已登录的账号现在是否仍然有效（存在且未被禁用）。

    为什么需要这个检查：账号被禁用后，cookie 免登录那条路确实走不通了
    （认证库发现用户名不在名单里会抛 User not authorized），
    但**本会话**的 authentication_status 仍是 True，
    login_gate() 里 `already` 一短路，就把人一直放行到 Cookie 过期为止——
    刚被禁用的管理员还能继续用管理页。这里主动核对一次，让「禁用」
    在下一次交互就生效。

    判定依据是「存储层里还在、且没被禁用」。三种情况一律**放行**（返回 True），
    因为它们都不该导致踢人：
    - 取不到用户名（异常状态，不误伤）；
    - 存储层已降级或报错（MySQL 抖一下不能让所有用户集体掉线）；
    - 账号不在存储层里（secrets 预置账号就是这种，它是兜底账号）。
    """
    username = st.session_state.get("username")
    if not username:
        return True
    try:
        store = get_store()
        if getattr(store, "note", None):
            return True  # 后端已降级，说明存储层有问题，不据此判定失效
        record = store.get_user(username)
    except Exception:  # noqa: BLE001
        return True
    if record is None:
        # 存储层里没有：可能是预置账号（合法），也可能真被删了
        return username in preset_usernames()
    return record.get("status") != STATUS_DISABLED


def preset_usernames() -> list[str]:
    """secrets 里的预置账号名。

    管理页把它们标成「预置」且只读：这些账号的事实来源是 secrets.toml，
    在页面上改了下一次加载就会被 secrets 覆盖回去，那还不如直接说不能改。
    """
    return sorted((_secret_config().get("usernames") or {}).keys())


# ---- 账号规则校验：注册路径由认证库把关，管理页新建/改密必须走同一套规则，
#      否则会「管理页能建出注册页建不出的账号」——两套标准迟早对不上。

def username_problem(username: str) -> str | None:
    """用户名校验：不合法返回中文原因，合法返回 None。

    认证库只接受 1~20 位的字母/数字/下划线/连字符（或邮箱形式），
    **不支持中文用户名**——这条限制来自它的正则，不是本项目另加的。
    """
    if not username:
        return "用户名不能为空"
    try:
        from streamlit_authenticator.utilities import Validator

        ok = Validator().validate_username(username)
    except Exception:  # noqa: BLE001 - 库换了内部结构也不放行
        ok = bool(re.match(r"^[a-zA-Z0-9_-]{1,20}$", username))
    if not ok:
        return "用户名只能是 1~20 位的字母、数字、下划线或连字符（不支持中文）"
    return None


def password_problem(password: str) -> str | None:
    """密码强度校验：不达标返回中文提示，达标返回 None（复用注册页同一套规则）。"""
    try:
        from streamlit_authenticator.utilities import Validator

        ok = Validator().validate_password(password)
    except Exception:  # noqa: BLE001
        ok = bool(re.match(
            r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)"
            r"(?=.*[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~])"
            r"[A-Za-z\d!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]{8,20}$",
            password,
        ))
    return None if ok else PASSWORD_HINT_CN


def hash_password(password: str) -> str:
    """把明文密码哈希成 bcrypt 字符串（管理页新建账号/重置密码用）。

    与认证库落盘用的格式一致（$2b$ 前缀），所以「库里存的」「secrets 里预置的」
    「认证库内存里生成的」三种哈希可以互相通用。
    """
    import bcrypt

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


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

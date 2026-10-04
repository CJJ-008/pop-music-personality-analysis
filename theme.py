# -*- coding: utf-8 -*-
"""主题切换（D35）：三套深色主题，运行时 CSS 覆盖层 + Cookie 跨会话记忆。

为什么是 CSS 覆盖层：.streamlit/config.toml 的 [theme] 在应用启动时就定死了，
Streamlit 没有运行中换主题的官方接口；本项目在 D22/D30/D34 已验证
「CSS 走 st.html 能生效、脚本不执行」的注入模式，所以主题 = 一组覆盖
页面关键表面（背景/侧边栏/按钮/选中态）的样式，切换时换注入的内容。

已知边界（浏览器实测 Streamlit 1.64）：
- 应用不暴露主题 CSS 变量，覆盖必须按 data-testid/data-baseweb 定位并加 !important；
- config.toml 的 primaryColor 被编译进组件内部样式，个别覆盖不到的焦点色仍是红色；
- 全部主题为深色系：浅色需要连文字颜色一起翻，覆盖面太大、易碎，第一批不做。

Cookie 记忆：读取用 st.context.cookies（服务端直读请求头，Streamlit 1.64），
写入沿用 D26 的前端 JS window.parent.document.cookie 模式，只在值变化时注入。
"""
import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "app_theme"   # 记忆主题的 cookie 名
STATE_KEY = "app_theme"     # 侧边栏切换器（st.pills）绑定的 session_state 键

# 每套主题的字段：accent 主色（按钮/选中态/链接）、accent_hover 悬停色、
# accent_soft 主色柔光（徽章描边/投影）、page 页面底色、sidebar 侧边栏与卡片底色、
# glow_a/glow_b 两处背景光晕
THEMES = {
    "neon": {
        "label": "🔴 霓虹夜曲",
        "accent": "#ff4b4b",
        "accent_hover": "#ff6b6b",
        "accent_soft": "rgba(255, 75, 75, .35)",
        "page": "#0e1117",
        "sidebar": "#161b26",
        "glow_a": "rgba(255, 75, 75, .10)",
        "glow_b": "rgba(124, 92, 255, .10)",
        "track_filter": "none",
    },
    "tech": {
        "label": "🔵 科技蓝",
        "accent": "#0ea5e9",
        "accent_hover": "#38bdf8",
        "accent_soft": "rgba(14, 165, 233, .35)",
        "page": "#050b18",
        "sidebar": "#0a1322",
        "glow_a": "rgba(34, 211, 238, .12)",
        "glow_b": "rgba(59, 130, 246, .12)",
        "track_filter": "hue-rotate(199deg)",
    },
    "cyber": {
        "label": "🟣 赛博紫",
        "accent": "#a855f7",
        "accent_hover": "#c084fc",
        "accent_soft": "rgba(168, 85, 247, .35)",
        "page": "#0a0714",
        "sidebar": "#120b22",
        "glow_a": "rgba(168, 85, 247, .12)",
        "glow_b": "rgba(236, 72, 153, .10)",
        "track_filter": "hue-rotate(271deg)",
    },
}
DEFAULT_ID = "neon"


def labels() -> list[str]:
    """切换器可选项（emoji + 中文名）。"""
    return [t["label"] for t in THEMES.values()]


def _label_to_id(label) -> str | None:
    for tid, t in THEMES.items():
        if t["label"] == label:
            return tid
    return None


def current_id() -> str:
    """当前主题 id：会话内选择（pills 绑定）优先，其次 Cookie，最后默认。

    pre-login（登录页）没有切换器，session_state 里不会有值，
    靠 Cookie 还原上次选择，因此登录页也跟随上次选的主题。
    """
    tid = _label_to_id(st.session_state.get(STATE_KEY))
    if tid:
        return tid
    try:
        cookie_val = st.context.cookies.get(COOKIE_NAME)
    except Exception:  # noqa: BLE001 - 非服务运行环境（脚本/测试）下没有 context
        cookie_val = None
    return cookie_val if cookie_val in THEMES else DEFAULT_ID


def current_preset() -> dict:
    return THEMES[current_id()]


def init_session() -> None:
    """登录后调用一次：把 Cookie 里记住的主题播种进 session_state。

    只在键不存在时播种（不覆盖用户本次会话里的实时切换）；
    播种成 label 而非 id，这样侧边栏 pills 的初始选中项直接对得上。
    """
    if STATE_KEY not in st.session_state:
        st.session_state[STATE_KEY] = current_preset()["label"]


def persist_cookie_js() -> None:
    """把当前主题写进浏览器 Cookie（跨会话记忆）。

    写入在前端完成（components.html 的 srcdoc 同源 iframe 可操作父页面，
    D26 退出登录就是这个思路）；用 session_state 记上次已写入的值，
    只有变化时才注入组件，避免每次重跑都多渲染一个空组件。
    """
    tid = current_id()
    if st.session_state.get("_theme_cookie_written") == tid:
        return
    js = (
        f"<script>window.parent.document.cookie = "
        f"'{COOKIE_NAME}={tid}; path=/; max-age=31536000; SameSite=Lax';</script>"
    )
    components.html(js, height=0)
    st.session_state["_theme_cookie_written"] = tid


# 全局覆盖层：换主题就是换这段里的几个 __TOKEN__。
# 用 token 替换而不用 str.format()——模板里全是 CSS 字面大括号，format 会误解析（D35 实测）；
# 颜色也不能用 var(--primary-color)——1.64 不暴露主题变量（D34 实测结论）。
_GLOBAL_CSS_TMPL = """<style>
/* 页面背景与顶栏 */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(1100px 520px at 12% -10%, __GLOW_A__, transparent 60%),
        radial-gradient(950px 520px at 90% 110%, __GLOW_B__, transparent 60%),
        __PAGE__ !important;
}
[data-testid="stHeader"] { background: transparent !important; }

/* 侧边栏：轻微纵向渐变，与主区区分开 */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, __SIDEBAR__ 0%, __PAGE__ 100%) !important;
}

/* 主色系：主按钮（侧边栏当前页、各页主操作）与表单提交按钮 */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stBaseButton-secondaryFormSubmit"] {
    background: __ACCENT__ !important;
    border-color: __ACCENT__ !important;
    color: rgb(255, 255, 255) !important;
}
[data-testid="stBaseButton-primary"]:hover,
[data-testid="stBaseButton-primaryFormSubmit"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    background: __ACCENT_HOVER__ !important;
    border-color: __ACCENT_HOVER__ !important;
    color: rgb(255, 255, 255) !important;
}
/* 次级按钮悬停点缀 */
[data-testid="stBaseButton-secondary"]:hover {
    border-color: __ACCENT__ !important;
    color: __ACCENT__ !important;
}

/* tabs 选中下划线与选中字色 */
[data-baseweb="tab-highlight"] { background-color: __ACCENT__ !important; }
[data-baseweb="tab"][aria-selected="true"] p { color: __ACCENT__ !important; }

/* pills 选中项（标签找歌手页的标签栏、主题切换器本身）。
   实测 1.64 的 st.pills 没有 stPills testid，渲染成 stButtonGroup 里的按钮：
   单选（主题切换器）是 role="radio"+aria-checked，多选（标签栏）是 button+aria-pressed，
   选中态默认是「主色 20% 透明底」 */
[data-testid="stButtonGroup"] [role="radio"][aria-checked="true"],
[data-testid="stButtonGroup"] button[aria-pressed="true"] {
    background: __ACCENT__ !important;
    border-color: __ACCENT__ !important;
    color: rgb(255, 255, 255) !important;
}
[data-testid="stButtonGroup"] [role="radio"]:focus-visible,
[data-testid="stButtonGroup"] button:focus-visible {
    outline-color: __ACCENT__ !important;
}

/* 滑块（流行度预测器）：
   手柄 = 包含 input[type=range] 的圆点；数值标签跟随主色；
   填充线是轨道上的「内联 linear-gradient」（每个滑块位置不同，不能整体覆盖，
   且永远按 config.toml 的红色生成），用 hue-rotate 把红转到主题色相——
   灰色轨道段无色相、不受影响。角度按各主题主色的色相写在预设里 */
[data-testid="stSlider"] div:has(> div > input[type="range"]) {
    background-color: __ACCENT__ !important;
    border-color: __ACCENT__ !important;
}
[data-testid="stSlider"] [class*="efbyxod4"] p { color: __ACCENT__ !important; }
[data-testid="stSlider"] [class*="efbyxod5"] { filter: __TRACK_FILTER__ !important; }
/* 进度条 */
[data-testid="stProgressBar"] > div > div { background-color: __ACCENT__ !important; }

/* 文本框聚焦描边（react-aria 结构，1.64） */
[data-testid="stTextInput"] .react-aria-TextField:focus-within > div {
    border-color: __ACCENT__ !important;
}

/* 链接色 */
[data-testid="stMarkdownContainer"] a { color: __ACCENT__ !important; }
</style>"""


def inject_global_css() -> None:
    """登录后的所有页面调用：按当前主题注入全局覆盖层。"""
    p = current_preset()
    css = (
        _GLOBAL_CSS_TMPL
        .replace("__ACCENT_HOVER__", p["accent_hover"])
        .replace("__ACCENT__", p["accent"])
        .replace("__PAGE__", p["page"])
        .replace("__SIDEBAR__", p["sidebar"])
        .replace("__GLOW_A__", p["glow_a"])
        .replace("__GLOW_B__", p["glow_b"])
        .replace("__TRACK_FILTER__", p["track_filter"])
    )
    st.html(css)

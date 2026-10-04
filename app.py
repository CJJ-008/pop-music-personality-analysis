# -*- coding: utf-8 -*-
"""Streamlit 歌手推荐器：什么性格的年轻人喜欢什么样的流行歌手？

八个页面（侧边栏按钮式导航；前七个所有人可见，第八个仅管理员）：
1. 数据总览 —— 项目规模、推荐方式导引、模型成绩单；
2. 按画像推荐 —— 3 个 K-Means 性格画像，查看各画像的流派与代表歌手；
3. 按性格标签找歌手 —— 用户自由勾选 37 个性格/生活方式/兴趣标签，
   系统按「标签 → 参考人群 → 流派亲和度 → 歌手」链路实时合成推荐；
4. 性格小测评 —— 25 道题算出五维得分，用 KNN 找最像的 101 人做推荐；
5. 歌手查询 —— 输入歌手名（实时联想），看 TA 的照片、代表作与数据画像，
   以及哪类性格画像最可能喜欢 TA（反向推荐）；
6. 描述找歌 —— 用自己的话描述想要的风格（情绪/快慢/乐器感/场景/流派/年代），
   按音频特征检索匹配的歌曲与歌手（基于内容的检索，词典解析、全程可解释）；
7. 流行度预测器 —— 拖动音频特征滑块，随机森林实时预测流行度。
8. 用户管理（仅管理员）—— 用户增删改、重置密码、启用/禁用、角色设置、登录日志。

数据源：只读取 outputs/tables/ 下已入库的分析结果表（不依赖原始数据），
因此克隆仓库或部署到 Streamlit Community Cloud 后无需重新跑分析、冷启动即可用。
分析逻辑见 src/，完整分析报告见 reports/。
登录认证见 auth.py（凭据存 st.secrets，角色与登录日志同在该模块）；
用户数据存哪由 user_store.py 决定——本地可走 MySQL，云端/exe 走 data/users.json。
专业知识点配 ❓ 问号弹窗（glossary.py），点开是给非专业用户的通俗解释。

本地运行：
    streamlit run app.py
"""
import html
import json
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from auth import (
    ADMIN_ROLE,
    PASSWORD_HINT_CN,
    hash_password,
    is_admin,
    load_credentials,
    login_gate,
    password_problem,
    preset_usernames,
    resolve_dirs,
    storage_note,
    username_problem,
)
from artist_photo import get_artist_photo
from glossary import head_kb, kb, kb_row
import style_search
import theme
from user_store import STATUS_ACTIVE, STATUS_DISABLED, fmt_local, get_store, norm_roles

# 结果表在打包后位于 _MEIPASS 只读资源目录，源码运行时就是项目根目录
RESOURCE_DIR, ROOT = resolve_dirs()
TAB = RESOURCE_DIR / "outputs" / "tables"

st.set_page_config(page_title="性格 × 流行歌手推荐器", page_icon="🎧", layout="wide")

# ---- 登录门禁：未登录会渲染登录/注册页并中断脚本，通过后继续渲染仪表盘 ----
authenticator, user_name, user_name_id = login_gate()

# ---- 主题（D35）：播种 Cookie 里记住的选择，再按当前主题注入全局覆盖 CSS ----
# 必须在 login_gate 之后：未登录时登录页的配色由 auth.py 自己按主题渲染
theme.init_session()
theme.inject_global_css()

# ---- 右上角账号图标：注入 Streamlit 顶栏，点开下拉可查看登录名并退出 ----
# 退出原理：认证库的「记住登录」cookie 由前端 JS 写入（CookieManager, path=/），
# 因此前端清除该 cookie 后整页刷新，新会话即回到登录页；
# 顶栏是 Streamlit 的静态骨架，组件重渲染不影响注入的图标（脚本幂等，防重复注入）
_display = html.escape(str(user_name or user_name_id))
_cookie = str(getattr(authenticator, "cookie_name", "") or "music_personality_app")
_account_js = r"""
<script>
(function () {
  var doc = window.parent.document;
  if (doc.getElementById('acct-chip')) return;   // 已注入过则跳过（重渲染幂等）
  var NAME = "__NAME__", COOKIE = "__COOKIE__";
  var host = doc.querySelector('[data-testid="stToolbar"]') ||
             doc.querySelector('header[data-testid="stHeader"]');
  if (!host) return;
  var wrap = doc.createElement('div');
  wrap.style.cssText = 'position:relative;display:flex;align-items:center;' +
    'flex:0 0 auto;pointer-events:auto;';
  wrap.innerHTML =
    '<div id="acct-chip" title="账号">' +
      '<span style="font-size:14px">👤</span>' +
      '<span>' + NAME + '</span>' +
      '<span style="font-size:10px;opacity:.7">▾</span></div>' +
    '<div id="acct-menu">' +
      '<div style="padding:9px 14px;font-size:12px;white-space:nowrap;' +
        'border-bottom:1px solid rgba(128,128,128,.25)">已登录：<b>' + NAME + '</b></div>' +
      '<div id="acct-logout" style="padding:9px 14px;font-size:13px;cursor:pointer;' +
        'user-select:none">🚪 退出登录</div></div>';
  var anchor = host.querySelector('[data-testid="stMainMenu"]');
  if (anchor && anchor.parentElement) anchor.parentElement.insertBefore(wrap, anchor);
  else host.appendChild(wrap);
  var chip = doc.getElementById('acct-chip'), menu = doc.getElementById('acct-menu');
  var bgc = (getComputedStyle(doc.body).backgroundColor || '').match(/\d+/g) || [255, 255, 255];
  var dark = (0.299 * bgc[0] + 0.587 * bgc[1] + 0.114 * bgc[2]) < 128;
  chip.style.cssText = 'display:flex;align-items:center;gap:6px;padding:3px 12px;' +
    'border-radius:16px;cursor:pointer;user-select:none;white-space:nowrap;' +
    'font-size:13px;line-height:22px;pointer-events:auto;color:inherit;' +
    'background:rgba(128,128,128,.16);border:1px solid rgba(128,128,128,.30)';
  menu.style.cssText = 'display:none;position:absolute;top:34px;right:0;min-width:170px;' +
    'border-radius:10px;overflow:hidden;z-index:1000001;' +
    'box-shadow:0 8px 24px rgba(0,0,0,.25);border:1px solid rgba(128,128,128,.35);' +
    'background:' + (dark ? '#1b2030;color:#fafafa' : '#ffffff;color:#262626');
  var style = doc.createElement('style');
  style.textContent = '#acct-chip:hover{background:rgba(128,128,128,.30)!important}' +
                      '#acct-logout:hover{background:rgba(128,128,128,.18)}';
  doc.head.appendChild(style);
  chip.addEventListener('click', function (e) {
    e.stopPropagation();
    menu.style.display = (menu.style.display === 'block') ? 'none' : 'block';
  });
  doc.addEventListener('click', function () { menu.style.display = 'none'; });
  doc.getElementById('acct-logout').addEventListener('click', function () {
    doc.cookie = COOKIE + '=; Max-Age=0; path=/';   // 清「记住登录」cookie
    window.parent.location.reload();                 // 刷新后回到登录页
  });
})();
</script>
""".replace("__NAME__", _display).replace("__COOKIE__", _cookie)
components.html(_account_js, height=0)


@st.cache_data
def load_csv(name: str, index_col: bool = False) -> pd.DataFrame:
    """读取分析结果表；index_col=True 表示首列是行索引。"""
    path = TAB / name
    if not path.exists():
        st.error(f"缺少结果表 outputs/tables/{name}。"
                 f"请先在本地依次运行 src/02~08 分析脚本，并确认 outputs/tables/ 已提交。")
        st.stop()
    return pd.read_csv(path, index_col=0 if index_col else None)


def esc(text) -> str:
    """展示用：把半角 $ 换成全角 ＄。

    歌手名 $uicideBoy$ 中的 $...$ 会被 Streamlit/plotly 当 LaTeX 数学公式
    解析而吞掉符号，全角替代可稳定显示且外观几乎一致。
    """
    return str(text).replace("$", "＄")


concl = load_csv("singer_conclusion_table.csv")
artists = load_csv("singer_top_by_genre.csv")
zscore = load_csv("profile_traits_zscore.csv", index_col=True)
demo = load_csv("profile_demographics.csv", index_col=True)
affinity = load_csv("tag_genre_affinity.csv", index_col=True)   # 标签 × 17 流派
tag_defs = load_csv("tag_definitions.csv")

PROFILES = demo.index.tolist()

# 问卷 17 流派 -> Spotify 6 大流派的展示名（与 singer_top_by_genre.csv 一致）；
# 5 个无对应项的流派不参与歌手匹配（数据集限制，如实标注）
CN2SP = {
    "流行": "流行", "摇滚": "摇滚", "摇滚乐": "摇滚", "金属/硬摇": "摇滚",
    "朋克": "摇滚", "另类": "摇滚", "嘻哈/说唱": "说唱",
    "舞曲": "电子舞曲", "电音": "电子舞曲", "拉丁": "拉丁",
    "爵士": "R&B", "雷鬼": "R&B",
}
UNMAPPED_GENRES = {"民谣", "乡村", "古典", "音乐剧", "歌剧"}


def genre_artists(genre_cn: str) -> pd.DataFrame:
    """某 Spotify 流派的 Top 歌手表（含排名）。"""
    top = (artists[artists["Spotify流派"] == genre_cn]
           .sort_values("平均流行度", ascending=False)
           .reset_index(drop=True))
    return top


def artist_bar(top: pd.DataFrame):
    """歌手流行度横向条形图（plotly）。"""
    fig = go.Figure(go.Bar(
        x=top["平均流行度"].iloc[::-1],
        y=[esc(a) for a in top["歌手"].iloc[::-1]],
        orientation="h",
        text=[f"{v:.1f}" for v in top["平均流行度"].iloc[::-1]],
        textposition="outside",
        marker_color="#4c72b0",
        hovertemplate="%{y}<br>平均流行度 %{x}<br>歌曲数 %{customdata} 首<extra></extra>",
        customdata=top["歌曲数"].iloc[::-1],
    ))
    fig.update_layout(
        height=max(320, 42 * len(top)),
        xaxis_title="平均流行度（0-100，Spotify 口径）",
        margin=dict(l=10, r=30, t=10, b=10))
    return fig


def recommend_section(genre_cn: str) -> None:
    """渲染一个流派的代表歌手：条形图 + 排名表 + 推荐名单。"""
    top = genre_artists(genre_cn)
    if top.empty:
        st.warning(f"流派「{genre_cn}」暂无歌手数据")
        return
    st.plotly_chart(artist_bar(top), width="stretch")
    table = top[["歌手", "歌曲数", "平均流行度"]].copy()
    table.index = table.index + 1
    table.index.name = "排名"
    st.dataframe(table, width="stretch", height=min(420, 35 * len(table) + 38))
    st.markdown(f"**推荐歌手**：{'、'.join(esc(a) for a in top['歌手'].head(5))}")


# ------------------------------------------------- 歌手搜索框（实时联想）----
@st.fragment
def artist_search_box(artists_all: pd.DataFrame) -> None:
    """歌手搜索框 + 实时联想：输入几个字母就出候选，点一下直接查询。

    单独包成 @st.fragment 是有意的：live 输入每停顿一次就触发重跑，
    隔离后只重跑这一小块，不会连带重绘照片、代表作表和音频图表；
    真正选定歌手（点候选、或唯一匹配自动选中）时才整页重绘一次。
    选中的歌手存在 st.session_state["artist_pick"]，由页面主体读取渲染。
    """
    query = (st.text_input("歌手名（输入几个字母即可，下面会自动联想）", "",
                           type="search", live="400ms", key="artist_query",
                           placeholder="例如 Ed、Taylor、justin") or "").strip()

    def commit(name: str | None) -> None:
        """记录当前选中的歌手；值真的变了才整页重绘（否则会无限重跑）。"""
        if st.session_state.get("artist_pick") == name:
            return
        if name is None:
            st.session_state.pop("artist_pick", None)
        else:
            st.session_state["artist_pick"] = name
        st.rerun(scope="app")

    if not query:
        commit(None)
        return

    # regex=False：歌手里有 A$AP Rocky、Ty Dolla $ign 这类带正则符号的名字，
    # 按字面匹配才搜得到（用户输入的就是歌手名的一部分，不是正则）
    matches = artists_all[artists_all["歌手"].str.contains(query, case=False, na=False,
                                                           regex=False)]
    if matches.empty:
        commit(None)
        st.warning(f"没有找到包含「{query}」的歌手（索引覆盖歌曲数≥5 的 "
                   f"{len(artists_all)} 位歌手）。试试更短的关键词。")
        return

    if len(matches) == 1:
        only = matches["歌手"].iloc[0]
        st.caption(f"唯一匹配：**{esc(only)}**")
        commit(only)          # 只剩一个候选时直接选中，省一次点击
        return

    st.caption(f"匹配到 {len(matches)} 位歌手（按平均流行度排序），点一下直接查看：")
    picked = st.pills("联想结果", matches["歌手"].head(8).tolist(),
                      selection_mode="single", key="artist_suggest",
                      label_visibility="collapsed")
    if picked:
        commit(picked)


# ------------------------------------------------- 描述找歌（第 7 页引擎）----
@st.fragment
def style_search_page(songs: pd.DataFrame, stats: pd.DataFrame,
                      examples: list[str]) -> None:
    """「💬 描述找歌」整页内容：描述 → 我理解成了什么 → 匹配歌曲与歌手。

    整页包成 @st.fragment：live 输入每次停顿都会重跑一次检索（28356 首歌的
    向量化打分约几十毫秒），隔离后不会连带重跑应用其它部分。

    数据边界（如实写进页面，不假装能做）：数据集只有音频特征，没有旋律/音高、
    歌词、乐器识别、歌手性别字段，所以"哼一段旋律""按歌词""找女声"这类都做不到，
    解析器会把这类词明确标注为"不支持"而不是静默忽略。
    """
    query_text = st.text_input("描述你想要的风格（情绪、快慢、乐器感、场景、流派、年代都可以）",
                               "", type="search", live="500ms", key="style_query",
                               placeholder="例如：钢琴伴奏的深夜抒情歌")

    # 示例短语：用 on_click 回调写 session_state（回调先于脚本执行，规避
    # "控件实例化后不可改值"的报错），点一下即填入并出结果
    example_cols = st.columns(len(examples))
    for col, ex in zip(example_cols, examples):
        with col:
            st.button(ex, key=f"style_ex_{ex}",
                      on_click=lambda e=ex: st.session_state.__setitem__("style_query", e))

    query_text = (query_text or "").strip()
    if not query_text:
        st.info("在上方输入描述开始找歌，或点一个示例试试；也可以混着写，"
                "例如「失恋后想听的慢歌」「小调忧郁的说唱」")
        kb_row("content_based", label="📖 名词小课堂：这种找歌方式是什么原理")
        return

    query = style_search.parse_query(query_text)

    # ---- 不支持的说法：识别得出但数据集没有对应信息，明说而不是静默忽略 ----
    if query.unsupported:
        for term, reason, advice in query.unsupported:
            st.warning(f"「{term}」我做不到：{reason}。{advice}")

    if query.empty:
        st.warning("没听懂你的描述。试试这些说法，或点上面的示例：")
        with st.expander("看看我能听懂哪些词（共 %d 个词条）" % len(style_search.LEXICON)):
            by_cat = {}
            for term, category, desc, *_ in style_search.LEXICON:
                by_cat.setdefault(category, []).append(term)
            for category, terms in by_cat.items():
                st.markdown(f"**{category}**：" + "、".join(terms))
        return

    # ---- 我理解成了什么：逐词展示解读，让推荐过程可核查 ----
    st.subheader("我理解成了")
    for term, _category, desc in query.hits:
        st.markdown(f"- **{term}** → {desc}")
    if query.unknown:
        st.caption("这些词我没听懂（已忽略）：" + "、".join(query.unknown)
                   + "；支持的说法点上面的词表展开看")
    if query.genres:
        st.caption("已按流派限定：" + "、".join(query.genres)
                   + "（明说了流派就只在该流派里找）")

    scored = style_search.score_songs(songs, stats, query, top_n=10)
    if scored.empty:
        st.warning("这个组合太冷门了，没找到匹配的歌曲——试试去掉一两个条件")
        return

    # ---- 匹配歌曲 ----
    head_kb(f"匹配的歌曲（候选 {len(songs):,} 首）", "content_based")
    st.dataframe(
        scored[["歌曲名", "歌手", "流派", "年份", "流行度", "匹配分", "为什么"]],
        hide_index=True, width="stretch",
        height=min(320, 35 * len(scored) + 38),
        column_config={
            "匹配分": st.column_config.ProgressColumn(
                "匹配分", min_value=0, max_value=1, format="%.2f"),
            "为什么": st.column_config.TextColumn("为什么匹配", width="large"),
        })
    st.caption("匹配分 = 85% × 风格匹配 + 15% × 流行度（混入流行度是为了不让结果全是冷门歌，"
               "口径与「混合推荐」一致）；「为什么匹配」取贡献最大的三个特征")

    # ---- 匹配歌手（带照片，可跳转歌手查询页）----
    st.subheader("匹配的歌手")
    artists = style_search.top_artists(scored, songs, top_n=5)

    def _goto_artist(name: str) -> None:
        """跳转到歌手查询页看该歌手：同时把名字填进那边的搜索框。

        只设 artist_pick 不够——歌手查询页的搜索框为空时会把选中清掉；
        带上名字过去，搜索联想会命中唯一匹配，画像直接渲染。
        按钮在 fragment 内，点它默认只重跑片段，必须显式整页重绘才会换页。
        """
        st.session_state["artist_pick"] = name
        st.session_state["artist_query"] = name
        st.session_state["page"] = "🔍 歌手查询"
        st.rerun(scope="app")

    for i, row in artists.iterrows():
        c1, c2 = st.columns([1, 4])
        with c1:
            photo = get_artist_photo(row["歌手"])
            if photo:
                st.image(photo["url"], width="stretch")
        with c2:
            st.markdown(f"**{esc(row['歌手'])}**　命中 **{row['命中歌曲数']}** 首，"
                        f"最高匹配分 {row['最高匹配分']:.2f}，代表曲目《{esc(row['代表歌曲'])}》")
            st.button("在歌手查询页看 TA 的完整画像", key=f"style_goto_{row['歌手']}",
                      on_click=_goto_artist, args=(row["歌手"],))

    st.caption("局限（如实说明）：这套检索只看数据集里有的 12 个音频特征与流派/年代信息，"
               "不支持描述旋律、歌词内容或歌手性别——数据集里没有这些数据，"
               "乐器类描述也是用「原声度/器乐占比」近似的。")


# ================================================= 页面8: 用户管理（仅管理员）====
def render_user_admin() -> None:
    """用户管理页：列表、新增、重置密码、启用/禁用、角色、资料、删除、登录日志。

    仅管理员可见——侧边栏不显示按钮，页面8 里还会再判一次（只藏按钮不算权限控制）。
    预置账号（secrets 里的）在列表里标出来但不可修改：它们的事实来源是
    secrets.toml，在页面上改了下次加载就被覆盖回去，不如直接说明不能改。
    """
    store = get_store()
    me = st.session_state.get("username")

    st.title("👤 用户管理")
    backend_desc = "MySQL 数据库" if store.backend == "mysql" else "data/users.json（文件）"
    st.caption(f"存储后端：**{store.source_label}** · {backend_desc}")

    # 操作类消息用「写入 session_state → 重跑 → 在顶部显示」的闪信模式：
    # 直接在表单里 st.success 会被紧接着的 st.rerun() 冲掉，用户看不到。
    flash = st.session_state.pop("_admin_flash", None)
    if flash:
        st.success(flash)

    note = getattr(store, "note", None) or storage_note()
    if note:
        st.warning(note)

    ok, message = store.ping()
    (st.success if ok else st.error)(f"存储自检：{message}")

    try:
        records = store.list_users()
    except Exception as exc:  # noqa: BLE001
        st.error(f"读取用户列表失败：{exc}")
        st.stop()

    credentials, _ = load_credentials()
    preset = set(preset_usernames())

    def _flash_and_rerun(text: str) -> None:
        st.session_state["_admin_flash"] = text
        st.rerun()

    # ---------------------------------------------------------- 用户列表 ----
    st.subheader("用户列表")
    rows = []
    for username, record in records.items():
        rows.append({
            "用户名": username,
            "来源": "预置（secrets）" if username in preset else store.source_label,
            "状态": "已禁用" if record.get("status") == STATUS_DISABLED else "启用中",
            "角色": "、".join(record.get("roles") or []) or "—",
            "邮箱": record.get("email") or "—",
            "姓名": f"{record.get('last_name', '')}{record.get('first_name', '')}".strip() or "—",
            "创建时间": fmt_local(record.get("created_at")),
            "最后登录": fmt_local(record.get("last_login_at")),
        })
    # 预置账号若不在存储里也要列出来——它是登录兜底，看不见才危险
    for username in sorted(preset - set(records)):
        entry = (credentials.get("usernames") or {}).get(username) or {}
        rows.append({
            "用户名": username,
            "来源": "预置（secrets）",
            "状态": "启用中",
            "角色": "、".join(norm_roles(entry.get("roles"))) or "—",
            "邮箱": entry.get("email") or "—",
            "姓名": f"{entry.get('last_name', '')}{entry.get('first_name', '')}".strip() or "—",
            "创建时间": "—",
            "最后登录": "—",
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 height=min(420, 35 * len(rows) + 38))
    st.caption("「预置（secrets）」的账号来自 `.streamlit/secrets.toml`，页面不可修改"
               "（改了下次加载会被 secrets 覆盖）；它们同时也是 MySQL 挂掉时的登录兜底。")

    # ---------------------------------------------------------- 新增用户 ----
    st.divider()
    st.subheader("新增用户")
    with st.form("admin_create_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        new_username = c1.text_input("用户名", help="1~20 位字母、数字、下划线或连字符，不支持中文")
        new_email = c2.text_input("邮箱（可留空）")
        c3, c4 = st.columns(2)
        new_last = c3.text_input("姓（可留空）")
        new_first = c4.text_input("名（可留空）")
        new_password = st.text_input("密码", type="password", help=PASSWORD_HINT_CN)
        new_roles = st.multiselect("角色", [ADMIN_ROLE, "user"], default=["user"],
                                   help="admin 可进入本页；user 只能用其余七个页面")
        if st.form_submit_button("创建用户", type="primary"):
            problem = username_problem(new_username) or password_problem(new_password)
            if problem:
                st.error(problem)
            elif not new_roles:
                st.error("至少选一个角色")
            else:
                try:
                    store.create_user(new_username, {
                        "email": new_email,
                        "first_name": new_first,
                        "last_name": new_last,
                        "password_hash": hash_password(new_password),
                        "roles": new_roles,
                        "status": STATUS_ACTIVE,
                    })
                    _flash_and_rerun(f"已创建用户「{new_username}」")
                except Exception as exc:  # noqa: BLE001 - 重名、库不可用等
                    st.error(f"创建失败：{exc}")

    # ------------------------------------------------------ 管理已有用户 ----
    st.divider()
    st.subheader("管理已有用户")
    editable = sorted(u for u in records if u not in preset)
    if not editable:
        st.caption("存储里还没有可管理的用户（预置账号的事实来源是 secrets.toml，页面不可改）。")
    else:
        target = st.selectbox("选择用户", editable, key="admin_target")
        record = records[target]
        is_self = target == me
        state = "已禁用" if record.get("status") == STATUS_DISABLED else "启用中"
        st.caption(f"`{target}` · {state} · 角色：{'、'.join(record.get('roles') or []) or '无'}"
                   + ("　←　这是你当前登录的账号，不能禁用或删除" if is_self else ""))

        tab_pwd, tab_role, tab_info, tab_danger = st.tabs(
            ["重置密码", "角色与状态", "修改资料", "删除账号"])

        with tab_pwd:
            with st.form("admin_reset_pwd", clear_on_submit=True):
                pwd = st.text_input("新密码", type="password", help=PASSWORD_HINT_CN)
                pwd2 = st.text_input("再输一次", type="password")
                if st.form_submit_button("重置密码", type="primary"):
                    problem = password_problem(pwd)
                    if problem:
                        st.error(problem)
                    elif pwd != pwd2:
                        st.error("两次输入的密码不一致")
                    else:
                        try:
                            store.set_password(target, hash_password(pwd))
                            _flash_and_rerun(f"已重置「{target}」的密码")
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"重置失败：{exc}")
            st.caption("密码只存 bcrypt 哈希，页面上无法查看原密码——忘记就只能重置。")

        with tab_role:
            with st.form("admin_set_role"):
                roles = st.multiselect("角色", [ADMIN_ROLE, "user"],
                                       default=record.get("roles") or ["user"])
                if st.form_submit_button("保存角色", type="primary"):
                    if not roles:
                        st.error("至少保留一个角色")
                    elif is_self and ADMIN_ROLE not in roles:
                        # 自保：取消自己的管理员角色 = 把自己锁在管理页外面
                        st.error("不能取消自己的管理员角色（否则你将无法再进入本页）")
                    else:
                        try:
                            store.set_roles(target, roles)
                            _flash_and_rerun(f"已更新「{target}」的角色")
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"保存失败：{exc}")

            disabled = record.get("status") == STATUS_DISABLED
            label = "✅ 启用该账号" if disabled else "🚫 禁用该账号"
            if st.button(label, key="admin_toggle_status",
                         disabled=is_self, help="不能禁用当前登录的账号" if is_self else None):
                try:
                    store.set_status(target, STATUS_ACTIVE if disabled else STATUS_DISABLED)
                    _flash_and_rerun(f"已{'启用' if disabled else '禁用'}「{target}」")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"操作失败：{exc}")
            st.caption("禁用不是删除：账号与密码都还在，只是登录时被过滤掉、登不进来，"
                       "随时可以再启用。")

        with tab_info:
            with st.form("admin_edit_info"):
                email = st.text_input("邮箱", value=record.get("email") or "")
                last_name = st.text_input("姓", value=record.get("last_name") or "")
                first_name = st.text_input("名", value=record.get("first_name") or "")
                if st.form_submit_button("保存资料", type="primary"):
                    try:
                        store.update_user(target, {
                            "email": email, "first_name": first_name, "last_name": last_name,
                        })
                        _flash_and_rerun(f"已更新「{target}」的资料")
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"保存失败：{exc}")

        with tab_danger:
            st.warning("删除是**不可恢复**的：账号与密码哈希都会从存储里移除。"
                       "如果只是想暂时不让登录，请用「角色与状态」里的禁用。")
            confirm = st.checkbox(f"我确认要永久删除「{target}」", key="admin_confirm_del")
            if st.button("删除账号", type="primary", disabled=is_self or not confirm,
                         key="admin_delete", help="不能删除当前登录的账号" if is_self else None):
                try:
                    store.delete_user(target)
                    _flash_and_rerun(f"已删除用户「{target}」")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"删除失败：{exc}")

    # ---------------------------------------------------------- 登录日志 ----
    st.divider()
    st.subheader("登录日志")
    try:
        logs = store.list_login_logs(limit=200)
    except Exception as exc:  # noqa: BLE001
        logs = []
        st.error(f"读取登录日志失败：{exc}")
    if logs:
        log_df = pd.DataFrame([{
            "时间": fmt_local(row["login_at"]),
            "用户名": row["username"],
            "结果": "成功" if row["success"] else "失败",
            "IP": row["ip"],
        } for row in logs])
        st.dataframe(log_df, width="stretch", hide_index=True,
                     height=min(420, 35 * len(log_df) + 38))
        st.caption("最多显示最近 200 条，时间按本机时区显示（存储里是 UTC）。"
                   "登录失败时认证库不记录用户输入的用户名，只有「账号确实存在、"
                   "只是密码错」这种情况能还原出来，其余如实记为「（未知用户）」。")
    else:
        st.caption("暂无登录记录。")


# ---------------------------------------------------------------- 侧边栏 ----
PAGES = ["📊 数据总览", "🎧 按画像推荐", "🏷️ 按性格标签找歌手",
         "📝 性格小测评", "🔍 歌手查询", "💬 描述找歌", "🎚️ 流行度预测器"]
ADMIN_PAGE = "👤 用户管理"

# 管理页只对管理员可见。注意这里只决定「显不显示按钮」，
# 真正的权限判断在页面8 的渲染分支里——用户完全可以自己把 session_state.page
# 改成 ADMIN_PAGE，只靠隐藏按钮不构成权限控制。
_IS_ADMIN = is_admin()
_VISIBLE_PAGES = PAGES + ([ADMIN_PAGE] if _IS_ADMIN else [])

with st.sidebar:
    # 按钮式导航：当前页高亮，点击即切换（替代 radio 的圆形勾选样式）
    if "page" not in st.session_state:
        st.session_state.page = _VISIBLE_PAGES[0]
    # 角色变化（例如管理员被降级）后会残留在已不可见的页名上，
    # 那时既没有按钮可点、页面也不渲染，会停在一片空白里，所以纠正回第一页
    if st.session_state.page not in _VISIBLE_PAGES:
        st.session_state.page = _VISIBLE_PAGES[0]
    page = st.session_state.page
    for p in _VISIBLE_PAGES:
        if st.button(p, key=f"nav_{p}", use_container_width=True,
                     type="primary" if p == page else "secondary") and p != page:
            st.session_state.page = p
            st.rerun()

    if page == "🎧 按画像推荐":
        st.header("选择性格画像")
        if "profile" not in st.session_state:
            st.session_state.profile = PROFILES[0]
        profile = st.session_state.profile
        for p in PROFILES:
            if st.button(f"{p}（{demo.loc[p, '人数']} 人）", key=f"prof_{p}",
                         use_container_width=True,
                         type="primary" if p == profile else "secondary") and p != profile:
                st.session_state.profile = p
                st.rerun()

    st.divider()
    st.caption(
        "**项目背景**\n\n"
        "基于 1010 名 15~30 岁年轻人的性格问卷（Kaggle Young People Survey）"
        "与 28356 首 Spotify 歌曲数据，通过 K-Means 聚类把年轻人分成 3 个性格画像，"
        "再结合画像的流派偏好与各流派 Top 歌手给出推荐。\n\n"
        f"画像间流派偏好差异经 Kruskal-Wallis 检验，17 个流派中 15 个显著（p<0.05）。"
    )
    kb("significance", label="❓ 什么是 p<0.05？")

    # ---- 完整分析报告入口（在线 + 离线）----
    st.divider()
    st.markdown("**📖 完整分析报告**")
    st.caption("想知道推荐结论是怎么算出来的？看这份全流程分析报告")
    _repo = "https://github.com/CJJ-008/pop-music-personality-analysis"
    report_url = f"{_repo}/blob/main/reports/{quote('流行音乐数据分析报告.ipynb')}"
    st.link_button("🔎 在线查看（GitHub 渲染）", report_url, use_container_width=True)
    html_path = RESOURCE_DIR / "reports" / "分析报告.html"
    if html_path.exists():
        st.download_button(
            "📥 下载离线报告（HTML）",
            data=html_path.read_bytes(),
            file_name="流行音乐数据分析报告.html",
            mime="text/html",
            use_container_width=True,
            help="自包含单文件，双击即可在浏览器打开，无需安装 Python")
    else:
        st.caption("离线 HTML 版未打包：源码运行时执行 src/07_build_report.py 生成")

    # ---- 主题风格切换（D35）：pills 即改即生效，选择写 Cookie 跨会话记住 ----
    st.divider()
    st.markdown("**🎨 主题风格**")
    st.pills("主题风格", options=theme.labels(), key=theme.STATE_KEY,
             label_visibility="collapsed")
    theme.persist_cookie_js()

# ============================================================ 页面0: 总览 ====
if page == "📊 数据总览":
    st.title("📊 数据总览")
    st.caption("一个用真实问卷与歌曲数据回答「什么性格的年轻人喜欢什么歌手」的项目")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("问卷受访者", "1,010 人", "15~30 岁 · 斯洛伐克")
    m2.metric("Spotify 歌曲", "28,356 首", "去重后 · 10,692 位歌手")
    m3.metric("性格画像", "3 类", "K-Means · 轮廓系数 0.170")
    m4.metric("推荐标签", "37 个", "性格 / 生活方式 / 兴趣 / 背景")
    kb_row("kmeans", label="📖 名词小课堂：K-Means 聚类 · 轮廓系数是什么")

    st.subheader("推荐方式怎么选")
    st.markdown(
        "- **🎧 按画像推荐**：三类专业画像（尽责自律 / 开放好奇 / 情绪稳定外向），"
        "展示性格雷达图、流派偏好与代表歌手；\n"
        "- **🏷️ 按性格标签找歌手**：勾选 37 个性格/生活方式/兴趣标签，"
        "系统圈出问卷中最符合的人群并实时合成推荐；\n"
        "- **📝 性格小测评**：答 25 道题（约 3 分钟），从 1010 人中找出与你最像的 101 人，"
        "生成专属推荐与性格雷达图；\n"
        "- **🔍 歌手查询**：反向推荐——输入歌手名，看哪类性格的人最可能喜欢 TA；\n"
        "- **🎚️ 流行度预测器**：拖动滑块调整歌曲的音频特征，实时预测流行度。")

    st.subheader("模型成绩单")
    cl = load_csv("classify_model_comparison.csv")
    rg = load_csv("regress_model_comparison.csv")
    ev = load_csv("recommender_eval.csv")

    c1, c2 = st.columns(2)
    with c1:
        head_kb("分类：预测性格画像（随机森林最优）", "random_forest", bold=True)
        st.dataframe(cl, width="stretch", height=min(240, 35 * len(cl) + 38))
    with c2:
        head_kb("回归：预测歌曲流行度（R² = 0.17）", "r2", bold=True)
        st.dataframe(rg, width="stretch", height=min(240, 35 * len(rg) + 38))

    head_kb("推荐效果评测（留一法，排除本人；详细解读见「性格小测评」页）",
            "loocv", bold=True)
    st.dataframe(ev, width="stretch", height=min(280, 35 * len(ev) + 38))
    st.caption("混合推荐（性格信号 + 流行度先验，α=0.4）平均排名 2.89，"
               "优于任何单一方法；KNN 亦显著优于随机猜。"
               "流派偏好主要由大众流行度驱动，性格是次要但真实的信号。")

    st.subheader("项目结构")
    st.caption("分析脚本 src/01~12 · 报告 reports/ · 技术栈档案 技术栈说明.md · "
               "本应用读取的全部结果表均在 outputs/tables/（已入库）")

# ============================================================ 页面1: 画像 ====
elif page == "🎧 按画像推荐":
    row = demo.loc[profile]

    st.title("🎧 性格 × 流行歌手推荐器")
    st.caption("选择左侧的性格画像，查看这类年轻人偏爱的音乐流派与代表歌手")

    st.header(f"【{profile}】")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("画像人数", f"{int(row['人数'])} 人",
              f"占比 {int(row['人数']) / int(demo['人数'].sum()):.1%}")
    m2.metric("女性占比", f"{row['女性占比']:.0%}")
    m3.metric("平均年龄", f"{row['平均年龄']:.1f} 岁")
    m4.metric("城市占比", f"{row['城市占比']:.0%}")
    kb_row("kmeans", label="📖 名词小课堂：这个画像来自 K-Means 聚类")

    # ---- 性格雷达图 + 五维解读 ----
    head_kb("性格侧写（五维人格代理指标）", "bigfive", "zscore")
    z_row = zscore.loc[profile]
    cats = list(z_row.index)

    col_radar, col_read = st.columns([2, 3])
    with col_radar:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[z_row[c] for c in cats] + [z_row[cats[0]]],
            theta=cats + [cats[0]],
            fill="toself", line_color="#4c72b0", name=profile))
        fig.add_trace(go.Scatterpolar(
            r=[0] * (len(cats) + 1), theta=cats + [cats[0]],
            mode="lines", line=dict(dash="dot", color="gray"),
            showlegend=False, hoverinfo="skip"))
        fig.update_layout(
            polar=dict(radialaxis=dict(title="z-score（0=全体平均）")),
            height=380, margin=dict(l=50, r=50, t=30, b=30),
            showlegend=False)
        st.plotly_chart(fig, width="stretch")

    with col_read:
        st.markdown("与全体平均相比（z-score > 0 表示高于平均）：")
        for trait in cats:
            v = z_row[trait]
            if v >= 0:
                st.markdown(f"- **{trait}**：高于平均 {v:+.2f} 个标准差")
            else:
                st.markdown(f"- {trait}：低于平均 {v:+.2f} 个标准差")

    # ---- 流派与歌手推荐 ----
    head_kb("音乐偏好与代表歌手", "relative_pref")
    st.caption("流派按「相对全体均值的偏好差异」排序（而非绝对分），才能体现画像的特征流派")

    sub = concl[concl["性格画像"] == profile]
    for rank_name in ["第1特征流派", "第2特征流派"]:
        r = sub[sub["偏好排名"] == rank_name].iloc[0]
        genre = r["特征流派"]

        st.markdown(f"#### {rank_name}：{genre}")
        k1, k2 = st.columns(2)
        k1.metric("相对偏好（相对全体均值）", f"{r['相对偏好']:+.2f}")
        k2.metric("绝对倾向分（1-5）", f"{r['绝对倾向分']:.2f}")
        if isinstance(r.get("解读提示"), str) and r["解读提示"]:
            st.info(r["解读提示"])
        recommend_section(genre)

    # ---- 页脚说明 ----
    st.divider()
    st.caption(
        "**结论口径说明**：两份数据集不是同一批人，通过「流派」桥接，"
        "本页结论是**画像层面的群体倾向**，不是个体因果关系；"
        "「尽责自律·宜人友善型」各流派偏好均衡、无明显特征流派，推荐结果为相对最接近者。"
    )

# ============================================================ 页面2: 标签 ====
elif page == "🏷️ 按性格标签找歌手":
    groups = json.loads((TAB / "tag_groups.json").read_text(encoding="utf-8"))

    st.title("🏷️ 按性格标签找歌手")
    st.caption("勾选贴近你的标签（可多选），系统会圈出问卷中最符合这些特征的人群，"
               "用他们的真实音乐偏好为你匹配流派与歌手")

    selected: list[str] = []
    g1, g2 = st.columns(2)
    g3, g4 = st.columns(2)
    for col_widget, group in zip((g1, g2, g3, g4), groups):
        with col_widget:
            picked = st.pills(f"{group}（{len(groups[group])}）", groups[group],
                              selection_mode="multi")
            selected.extend(picked)

    # ---- 标签栏左右滚动按钮 ----
    # pills 行内容超宽时被静默截断（容器 overflow:auto 但无可见滚动条，鼠标无法拖动）。
    # 注入分两半：CSS 用 st.html（样式能生效，但脚本不会执行）；JS 必须用
    # components.html 的 srcdoc 同源 iframe——它可以从 iframe 内部操作父页面 DOM。
    st.html("""<style>
  div[data-testid="stButtonGroup"] > div { scrollbar-width: none; }
  div[data-testid="stButtonGroup"] > div::-webkit-scrollbar { display: none; }
  .tag-scroll-btn {
    position: absolute; top: 50%; transform: translateY(-50%);
    z-index: 20; width: 26px; height: 26px; border-radius: 50%;
    border: 1px solid rgba(250,250,250,.3);
    background: rgba(30,30,30,.85); color: #fafafa;
    font-size: 15px; line-height: 1; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  .tag-scroll-btn:hover { background: rgba(90,90,90,.95); }
  .tag-scroll-btn.left { left: 2px; }
  .tag-scroll-btn.right { right: 2px; }
</style>
""")
    # 自愈式注入（D30）：脚本执行时机与 pills 渲染存在竞态——脚本跑得比 pills 快时
    # 一行都找不到，旧版「找不到行就不重试」的逻辑会直接退出，按钮从此消失。
    # 改为持续观察父页面：DOM 变化 / 窗口缩放 / 字体加载完成都重新扫一遍，
    # 任何时刻发现溢出行就补挂按钮（navReady 防重复），从此与渲染顺序无关。
    components.html("""
<script>
(function () {
  var doc = window.parent.document;
  try { doc.defaultView.__tagScrollAlive = (doc.defaultView.__tagScrollAlive || 0) + 1; } catch (e) {}

  function decorate() {
    doc.querySelectorAll('[data-testid="stButtonGroup"] > div').forEach(function (row) {
      if (row.dataset.navReady === "1") return;
      if (row.scrollWidth <= row.clientWidth + 4) return;  // 没溢出的行不需要按钮
      row.dataset.navReady = "1";
      var wrap = row.parentElement;
      wrap.style.position = "relative";
      function mkBtn(side, label, dx) {
        var b = doc.createElement("button");
        b.className = "tag-scroll-btn " + side;
        b.textContent = label;
        b.title = side === "left" ? "向左滚动" : "向右滚动";
        b.addEventListener("click", function (e) {
          e.preventDefault();
          row.scrollBy({ left: dx, behavior: "smooth" });
        });
        wrap.appendChild(b);
      }
      mkBtn("left", "‹", -220);
      mkBtn("right", "›", 220);
    });
  }

  // 触发器合并：页面任何 DOM 变化 / 窗口缩放 / 字体加载完成，都安排一次重扫
  var pending = null;
  function schedule() {
    if (pending) return;
    pending = setTimeout(function () { pending = null; decorate(); }, 120);
  }
  if (doc.body) new MutationObserver(schedule).observe(doc.body,
      { childList: true, subtree: true });
  doc.defaultView.addEventListener("resize", schedule);
  if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(schedule);
  decorate();
})();
</script>
""", height=1)

    # 互斥提示：双极成对标签同时选择会相互抵消
    pairs = [("外向爱社交", "安静内向"), ("自律可靠", "随性散漫"),
             ("情绪稳定", "感性敏感"), ("好奇开放", "务实传统"),
             ("友善体贴", "直率独立"), ("城市青年", "小镇青年")]
    clash = [p for p in pairs if p[0] in selected and p[1] in selected]
    if clash:
        st.info("提示：" + "、".join("与".join(p) for p in clash) +
                " 为相反方向的标签，同时选择时两者的偏好影响会相互抵消。")

    if not selected:
        st.info("请至少选择一个标签，例如：好奇开放 + 居家宅 + 追星族")
        st.stop()

    defs = tag_defs.set_index("标签")
    combo = affinity.loc[selected].mean()          # 多标签亲和度取平均
    combo_sorted = combo.sort_values(ascending=False)

    # ---- 参考人群规模 ----
    sizes = defs.loc[selected, "参考人数"]
    st.caption(f"本次推荐参考了 {len(selected)} 个标签，"
               f"每个标签取问卷 1010 人中最符合的前 30%（约 "
               f"{int(sizes.min())}~{int(sizes.max())} 人）的流派偏好，取平均后合成。")

    # ---- 17 流派亲和度条形图 ----
    head_kb("你的人群画像偏爱哪些流派", "relative_pref")
    sorted_genres = combo_sorted.index.tolist()
    fig = go.Figure(go.Bar(
        x=combo_sorted.values[::-1],
        y=sorted_genres[::-1],
        orientation="h",
        marker_color=["#c44e52" if g in UNMAPPED_GENRES else "#4c72b0"
                      for g in sorted_genres[::-1]],
        text=[f"{v:+.2f}" for v in combo_sorted.values[::-1]],
        textposition="outside",
        hovertemplate="%{y}<br>流派亲和度 %{x:+.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=max(380, 26 * len(sorted_genres)),
        xaxis_title="流派亲和度（相对全体的偏好差异，越大越偏爱）",
        margin=dict(l=10, r=40, t=10, b=10))
    st.plotly_chart(fig, width="stretch")
    st.caption("红色 = 该流派在歌曲数据集中没有对应歌手数据（民谣/乡村/古典/音乐剧/歌剧），"
               "仅作偏好参考，不参与歌手匹配")

    # ---- 映射到 Spotify 六大流派 ----
    sp_scores: dict[str, list[float]] = {}
    for gcn, v in combo.items():
        target = CN2SP.get(gcn)
        if target:
            sp_scores.setdefault(target, []).append(v)
    sp_aff = {g: sum(v) / len(v) for g, v in sp_scores.items()}
    sp_sorted = sorted(sp_aff.items(), key=lambda kv: kv[1], reverse=True)

    st.subheader("为你推荐的歌手")
    w_min, w_max = min(sp_aff.values()), max(sp_aff.values())
    flat = w_max - w_min < 1e-9
    if flat:
        st.info("所选标签组合的流派偏好较为均衡，以下按细微差异给出参考推荐。")

    top10_rows = []
    for rank_name, (genre_cn, aff) in enumerate(sp_sorted[:2], 1):
        st.markdown(f"#### 第{rank_name}匹配流派：{genre_cn}（亲和度 {aff:+.2f}）")
        recommend_section(genre_cn)
        w = 0.5 if flat else (aff - w_min) / (w_max - w_min)
        gtop = genre_artists(genre_cn)
        for _, r in gtop.iterrows():
            pop_norm = r["平均流行度"] / 100
            top10_rows.append({"歌手": r["歌手"], "流派": genre_cn,
                               "平均流行度": r["平均流行度"],
                               "综合得分": round(w * pop_norm, 4)})

    top10 = (pd.DataFrame(top10_rows)
             .drop_duplicates(subset="歌手")
             .sort_values("综合得分", ascending=False)
             .head(10)
             .reset_index(drop=True))
    top10.index = top10.index + 1
    top10.index.name = "名次"
    st.markdown("#### 综合推荐 Top10")
    st.caption("综合得分 = 流派匹配度（归一化）× 歌手平均流行度（归一化），跨流派合并排序")
    st.dataframe(top10, width="stretch", height=min(460, 35 * len(top10) + 38))

    # ---- 推荐依据 ----
    with st.expander("查看推荐依据（每个标签最偏好的流派）"):
        for tag in selected:
            row_a = affinity.loc[tag].sort_values(ascending=False).head(3)
            n = int(defs.loc[tag, "参考人数"])
            st.markdown(f"**{tag}**（参考人群 {n} 人，{defs.loc[tag, '描述']}）："
                        + "、".join(f"{g} {v:+.2f}" for g, v in row_a.items()))

    st.divider()
    st.caption("**结论口径说明**：标签亲和度来自问卷 1-5 打分与全体均值的差，"
               "歌手匹配只覆盖 Spotify 数据集的六大流派；结论是**画像层面的群体倾向**，"
               "不是个体因果关系。")

# ============================================================ 页面3: 测评 ====
elif page == "📝 性格小测评":
    QUIZ_TRAITS = ["外向社交", "尽责自律", "情绪稳定", "开放好奇", "宜人友善"]
    SCALE = ["1 完全不同意", "2 比较不同意", "3 一般", "4 比较同意", "5 完全同意"]
    questions = json.loads((TAB / "quiz_questions.json").read_text(encoding="utf-8"))
    stats = load_csv("quiz_population_stats.csv", index_col=True)
    basis = load_csv("quiz_basis.csv", index_col=True)

    st.title("📝 性格小测评")
    st.caption("回答 25 道小题，系统会从 1010 名问卷受访者中找出与你性格最像的人群，"
               "用他们的真实音乐偏好为你推荐流派与歌手")
    kb_row("bigfive", "knn", label="📖 名词小课堂：大五人格 · KNN 是什么")

    with st.form("quiz_form", clear_on_submit=False):
        saved = st.session_state.get("quiz_saved", {})
        qn = 0
        for dim in QUIZ_TRAITS:
            st.markdown(f"**{dim}**")
            if dim == "情绪稳定":
                st.caption("本组题目按你的真实感受选择即可，系统会自动换算")
            for q in questions:
                if q["维度"] != dim:
                    continue
                qn += 1
                # saved 存的是 0 基下标（index 参数要求 0~4，存 1~5 会抛
                # StreamlitValueOutOfRangeError，用户一改答案就整页报错）
                st.radio(f"{qn}. {q['题干']}", SCALE,
                         index=saved.get(qn), horizontal=True, key=f"quiz_{qn}")
        submitted = st.form_submit_button("提交，看我的音乐人格", use_container_width=True)
        _ = submitted  # 提交按钮触发重跑；结果在下方按"是否答完"统一渲染

    answers = [st.session_state.get(f"quiz_{i}") for i in range(1, len(questions) + 1)]
    if any(a is None for a in answers):
        st.info("还有题目没答完。答完 25 题并点击提交，即可生成你的音乐人格与专属推荐")
        st.stop()

    # ---- 计分：与 02/09 脚本同口径（反向题 6-分值，维度取均值）----
    user_raw = {t: [] for t in QUIZ_TRAITS}
    for i, q in enumerate(questions):
        v = int(answers[i][0])
        if q["反向计分"]:
            v = 6 - v
        user_raw[q["维度"]].append(v)
    user_trait = {t: sum(v) / len(v) for t, v in user_raw.items()}
    # 存 0 基下标供 index= 回填；计分用上面的 user_raw（取自原始选项值）
    st.session_state["quiz_saved"] = {i: int(a[0]) - 1 for i, a in enumerate(answers, 1)}

    user_z = pd.Series({t: (user_trait[t] - stats.loc[t, "均值"]) / stats.loc[t, "标准差"]
                        for t in QUIZ_TRAITS})

    # ---- KNN：五维 z 空间里找最相似的 10% 人群 ----
    # 注意：basis 的列名带 z_ 前缀（z_外向社交…），而 user_z 的索引是维度名（外向社交…）。
    # 必须先去掉前缀再相减——pandas 按索引对齐，标签对不上会静默产生全 NaN，
    # 而 .sum() 默认跳过 NaN，最终所有人的距离都变成 0，导致无论怎么答题都推荐同一批人。
    zcols = [c for c in basis.columns if c.startswith("z_")]
    zbasis = basis[zcols].copy()
    zbasis.columns = [c[len("z_"):] for c in zcols]
    dist = ((zbasis - user_z) ** 2).sum(axis=1) ** 0.5
    if dist.isna().any() or dist.max() == 0:
        st.error("相似度计算异常（维度未对齐），请把此问题反馈给开发者。")
        st.stop()
    k = max(50, int(round(len(basis) * 0.10)))
    cohort_idx = dist.nsmallest(k).index
    genre_cols = [c for c in basis.columns if not c.startswith("z_")]
    aff = (basis.loc[cohort_idx, genre_cols].mean() - basis[genre_cols].mean())
    aff_sorted = aff.sort_values(ascending=False)

    st.success(f"提交成功！从问卷中找到了 **{k} 位与你性格最像的人**（最相似前 10%），"
               "以下是他们的真实音乐偏好")
    st.subheader("你的音乐人格")
    col_radar, col_read = st.columns([2, 3])
    with col_radar:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=[user_z[c] for c in QUIZ_TRAITS] + [user_z[QUIZ_TRAITS[0]]],
            theta=QUIZ_TRAITS + [QUIZ_TRAITS[0]],
            fill="toself", line_color="#c44e52", name="你"))
        fig.add_trace(go.Scatterpolar(
            r=[0] * (len(QUIZ_TRAITS) + 1), theta=QUIZ_TRAITS + [QUIZ_TRAITS[0]],
            mode="lines", line=dict(dash="dot", color="gray"),
            showlegend=False, hoverinfo="skip"))
        fig.update_layout(
            polar=dict(radialaxis=dict(title="z-score（0=全体平均）")),
            height=380, margin=dict(l=50, r=50, t=30, b=30), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with col_read:
        kb("zscore")
        st.markdown("你的五维得分（1-5 分制）与 1010 人平均水平对比：")
        for t in QUIZ_TRAITS:
            dz = user_z[t]
            tone = "**" if dz > 0.3 or dz < -0.3 else ""
            direction = "高于" if dz > 0 else "低于"
            st.markdown(f"- {tone}{t}{tone}：{user_trait[t]:.2f} 分，"
                        f"{direction}全体平均 {dz:+.2f} 个标准差")

    st.subheader("和你最像的人偏爱哪些流派")
    st.caption(f"流派亲和度 = 与你最像的 {k} 人的流派均分 − 全体均分；"
               "红色流派在歌曲数据集中无对应歌手，仅作偏好参考")
    sorted_genres = aff_sorted.index.tolist()
    fig2 = go.Figure(go.Bar(
        x=aff_sorted.values[::-1], y=sorted_genres[::-1], orientation="h",
        marker_color=["#c44e52" if g in UNMAPPED_GENRES else "#4c72b0"
                      for g in sorted_genres[::-1]],
        text=[f"{v:+.2f}" for v in aff_sorted.values[::-1]], textposition="outside",
        hovertemplate="%{y}<br>流派亲和度 %{x:+.2f}<extra></extra>"))
    fig2.update_layout(
        height=max(380, 26 * len(sorted_genres)),
        xaxis_title="流派亲和度（相对全体的偏好差异）",
        margin=dict(l=10, r=40, t=10, b=10))
    st.plotly_chart(fig2, width="stretch")

    st.subheader("为你推荐的歌手")
    sp_scores: dict[str, list[float]] = {}
    for gcn, v in aff.items():
        target = CN2SP.get(gcn)
        if target:
            sp_scores.setdefault(target, []).append(v)
    sp_aff = {g: sum(v) / len(v) for g, v in sp_scores.items()}
    sp_sorted = sorted(sp_aff.items(), key=lambda kv: kv[1], reverse=True)
    w_min, w_max = min(sp_aff.values()), max(sp_aff.values())

    top10_rows = []
    for rank_name, (genre_cn, aff_v) in enumerate(sp_sorted[:2], 1):
        st.markdown(f"#### 第{rank_name}匹配流派：{genre_cn}（亲和度 {aff_v:+.2f}）")
        recommend_section(genre_cn)
        w = 0.5 if w_max - w_min < 1e-9 else (aff_v - w_min) / (w_max - w_min)
        for _, r in genre_artists(genre_cn).iterrows():
            top10_rows.append({"歌手": r["歌手"], "流派": genre_cn,
                               "平均流行度": r["平均流行度"],
                               "综合得分": round(w * r["平均流行度"] / 100, 4)})
    top10 = (pd.DataFrame(top10_rows)
             .drop_duplicates(subset="歌手")
             .sort_values("综合得分", ascending=False)
             .head(10).reset_index(drop=True))
    top10.index = top10.index + 1
    top10.index.name = "名次"
    st.markdown("#### 综合推荐 Top10")
    st.caption("综合得分 = 流派匹配度（归一化）× 歌手平均流行度（归一化），跨流派合并排序")
    st.dataframe(top10, width="stretch", height=min(460, 35 * len(top10) + 38))

    st.divider()
    st.caption("**结论口径说明**：测评把你与 1010 名受访者做相似度匹配，"
               "推荐来自与你最像的人群的真实打分，是**画像层面的群体倾向**，不是个体因果关系。")

# ============================================================ 页面4: 歌手查询 ====
elif page == "🔍 歌手查询":
    artists_all = load_csv("artist_index.csv")
    ref = load_csv("artist_overall_reference.csv").iloc[0]
    prof_rel = load_csv("profile_genre_relative.csv", index_col=True)
    top_tracks = load_csv("artist_top_tracks.csv")

    st.title("🔍 歌手查询")
    st.caption("输入歌手名（输入几个字母就会自动联想），查看 TA 的照片、代表作与数据画像，"
               "以及哪类性格的人最可能喜欢 TA")

    artist_search_box(artists_all)

    pick = st.session_state.get("artist_pick")
    if not pick:
        st.info("在上方输入歌手名开始查询，例如 Ed Sheeran、Billie Eilish、DaBaby")
        st.stop()
    row = artists_all[artists_all["歌手"] == pick].iloc[0]

    genre_cn = row["流派中文"]
    c_photo, c_body = st.columns([1, 3.4])
    with c_photo:
        # 照片从公开图源实时获取（Spotify 官方优先、网易云兜底），取不到就显示占位框，
        # 不影响页面其它内容——详见 artist_photo.py
        photo = get_artist_photo(row["歌手"])
        if photo:
            st.image(photo["url"], width="stretch")
            src = (f"[{photo['provider']}]({photo['source_url']})"
                   if photo["source_url"] else photo["provider"])
            st.caption(f"照片来源：{src}")
        else:
            st.markdown(
                "<div style='aspect-ratio:1;display:flex;align-items:center;"
                "justify-content:center;font-size:38px;border-radius:10px;"
                "border:1px dashed rgba(128,128,128,.45)'>🎤</div>",
                unsafe_allow_html=True)
            st.caption("未找到公开照片（照片需联网获取）")
    with c_body:
        st.header(f"🎤 {esc(row['歌手'])}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("主流派别", genre_cn)
        m2.metric("歌曲数", f"{int(row['歌曲数'])} 首")
        m3.metric("平均流行度", f"{row['平均流行度']:.1f}",
                  f"{row['平均流行度'] - ref['平均流行度']:+.1f} vs 全体")
        m4.metric("发行年份中位数", f"{int(row['发行年份中位数'])}")
        kb_row("popularity", label="📖 名词小课堂：流行度 0-100 是什么")

    # 代表作：该歌手在数据集内最热门的歌曲
    head_kb("代表作（数据集内最热门的歌曲）", "top_tracks")
    tr = top_tracks[top_tracks["歌手"] == row["歌手"]].sort_values("排名")
    if tr.empty:
        st.info("该歌手在本项目数据集中没有单曲记录")
    else:
        st.dataframe(
            tr[["排名", "歌曲名", "流行度", "专辑", "发行年份"]],
            hide_index=True, width="stretch", height=min(240, 35 * len(tr) + 38),
            column_config={
                "排名": st.column_config.NumberColumn("排名", width="small"),
                "流行度": st.column_config.ProgressColumn(
                    "流行度", min_value=0, max_value=100, format="%d"),
                "发行年份": st.column_config.NumberColumn("发行年份", format="%d"),
            })
        st.caption(f"口径：从本项目 28,356 首 Spotify 歌曲中，取该歌手播放热度"
                   f"（流行度）最高的 {len(tr)} 首——不是完整作品年表，"
                   "数据集没收录的歌不会出现在这里；"
                   "流行度为 0 表示 Spotify 未给出该曲热度。")

    # 音频特征与全体歌手平均对比
    head_kb("音频特征（与全体歌手平均对比）", "audio_features")
    feature_cn = {"danceability": "舞蹈性", "energy": "能量", "valence": "情绪效价",
                  "acousticness": "原声度", "instrumentalness": "器乐占比",
                  "liveness": "现场感", "speechiness": "语音占比"}
    diff_rows = []
    for k, cn in feature_cn.items():
        v, o = row[f"平均{k}"], ref[f"平均{k}"]
        diff_rows.append({"特征": cn, "该歌手": round(v, 3), "全体平均": round(o, 3),
                          "差异": round(v - o, 3)})
    diff_df = pd.DataFrame(diff_rows)
    fig = go.Figure(go.Bar(
        x=diff_df["差异"], y=diff_df["特征"], orientation="h",
        marker_color=["#c44e52" if d > 0 else "#4c72b0" for d in diff_df["差异"]],
        text=[f"{d:+.3f}" for d in diff_df["差异"]], textposition="outside",
        hovertemplate="%{y}<br>该歌手 %{customdata[0]} | 全体 %{customdata[1]}<extra></extra>",
        customdata=diff_df[["该歌手", "全体平均"]].values))
    fig.update_layout(height=340, margin=dict(l=10, r=40, t=10, b=10),
                      xaxis_title="与全体歌手平均的差异（红=更高，蓝=更低）")
    st.plotly_chart(fig, width="stretch")

    # 反向推荐：哪类画像最可能喜欢 TA
    head_kb("哪类性格画像最可能喜欢 TA", "relative_pref")
    if genre_cn in prof_rel.columns:
        pr = prof_rel[genre_cn].sort_values(ascending=False)
        st.markdown(f"该歌手的主流派别是 **{genre_cn}**。各画像对该流派的偏好差异：")
        for prof_name, v in pr.items():
            icon = "🔴" if v > 0.1 else ("🔵" if v < -0.1 else "⚪")
            st.markdown(f"- {icon} **{prof_name}**：{v:+.2f}"
                        + ("（明显高于平均）" if v > 0.1 else
                           "（明显低于平均）" if v < -0.1 else "（接近平均）"))
        st.caption("基于三个画像的流派偏好差异推算：歌手流派 → 各画像对该流派的亲和度。"
                   "是画像层面的推断，不是因果结论。")
    else:
        st.warning(f"流派「{genre_cn}」暂无画像偏好数据")

# ============================================================ 页面6: 预测器 ====
elif page == "🎚️ 流行度预测器":
    import joblib
    import numpy as np

    model_path = RESOURCE_DIR / "outputs" / "models" / "popularity_model.joblib"

    @st.cache_resource
    def load_model(path):
        return joblib.load(path)

    st.title("🎚️ 流行度预测器")
    st.caption("拖动滑块调整歌曲的音频特征，训练好的随机森林模型会实时预测这首歌的流行度（0-100）")

    payload = load_model(str(model_path))
    model = payload["model"]
    feature_cols = payload["feature_cols"]
    audio = payload["audio_features"]

    st.info(f"模型：随机森林回归（120 棵树），测试集 R² = {payload['test_r2']}。"
            "模型只能解释流行度差异的一小部分（R²≈0.17），"
            "预测值应理解为**大致区间**而非精确值——这正是本项目回归分析的核心发现："
            "歌曲走红主要由宣发与传播驱动，而非音频特征本身。")
    kb_row("random_forest", "r2", "audio_features",
           label="📖 名词小课堂：随机森林 · R² · 音频特征")

    g1, g2 = st.columns(2)
    with g1:
        danceability = st.slider("舞蹈性", 0.0, 1.0, 0.7, 0.01)
        energy = st.slider("能量", 0.0, 1.0, 0.6, 0.01)
        valence = st.slider("情绪效价（0=悲伤 1=欢快）", 0.0, 1.0, 0.5, 0.01)
        acousticness = st.slider("原声度", 0.0, 1.0, 0.2, 0.01)
        speechiness = st.slider("语音占比", 0.0, 1.0, 0.1, 0.01)
    with g2:
        instrumentalness = st.slider("器乐占比", 0.0, 1.0, 0.02, 0.01)
        liveness = st.slider("现场感", 0.0, 1.0, 0.15, 0.01)
        loudness = st.slider("响度 (dB)", -60.0, 0.0, -6.0, 0.5)
        tempo = st.slider("节奏 (BPM)", 50.0, 250.0, 120.0, 1.0)
        duration_min = st.slider("时长（分钟）", 0.5, 10.0, 3.5, 0.1)

    genre_key = st.selectbox("流派", list(payload["genre_options"].keys()),
                             format_func=lambda k: payload["genre_options"][k])
    year = st.slider("发行年份", 1956, 2020, 2019, 1)

    row = {
        "danceability": danceability, "energy": energy, "valence": valence,
        "acousticness": acousticness, "speechiness": speechiness,
        "instrumentalness": instrumentalness, "liveness": liveness,
        "loudness": loudness, "tempo": tempo,
        "duration_ms": duration_min * 60 * 1000, "key": 0, "mode": 1,
        "release_year": year,
    }
    for g in payload["genre_options"]:
        row[g] = 1 if g == genre_key else 0
    X = pd.DataFrame([row])[feature_cols]

    pred = model.predict(X)[0]
    m1, m2 = st.columns(2)
    m1.metric("预测流行度", f"{pred:.0f} / 100")
    m2.metric("对比全体歌曲中位数", f"{pred - 43:.0f} 分",
              f"{'高于' if pred > 43 else '低于'}中位数 43")

    st.progress(min(pred / 100, 1.0))

    imp = load_csv("predictor_feature_importance.csv", index_col=True)
    head_kb("模型眼中最重要的因素 Top10", "feature_importance")
    top = imp.head(10).iloc[::-1]
    fig = go.Figure(go.Bar(x=top["重要性"], y=top.index, orientation="h", marker_color="#55a868"))
    fig.update_layout(height=380, margin=dict(l=10, r=30, t=10, b=10),
                      xaxis_title="特征重要性（不纯度下降）")
    st.plotly_chart(fig, width="stretch")
    st.caption("注意：发行年份是最强预测因子——流行度指标存在「新歌优势」。"
               "这与回归分析的结论一致：歌曲走红主要由宣发与传播驱动。")

# ============================================================ 页面7: 描述找歌 ====
elif page == "💬 描述找歌":
    songs_all = load_csv("style_song_matrix.csv")
    feat_stats = load_csv("style_feature_stats.csv", index_col=True)
    style_examples = json.loads((TAB / "style_examples.json").read_text(encoding="utf-8"))

    st.title("💬 描述找歌")
    st.caption("用自己的话描述想要的风格——情绪、快慢、乐器感、场景、流派、年代都可以，"
               "系统按音频特征检索出最匹配的歌曲与歌手")

    style_search_page(songs_all, feat_stats, style_examples)

# ============================================================ 页面8: 用户管理 ====
elif page == ADMIN_PAGE:
    # 双重判断：侧边栏已经藏了按钮，这里再挡一次。
    # 只藏按钮不是权限控制——page 存在 session_state 里，用户能自己改。
    if not _IS_ADMIN:
        st.error("用户管理仅对管理员开放。")
        st.stop()
    render_user_admin()

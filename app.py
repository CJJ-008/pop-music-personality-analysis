# -*- coding: utf-8 -*-
"""Streamlit 歌手推荐器：什么性格的年轻人喜欢什么样的流行歌手？

两个推荐页面：
1. 按画像推荐 —— 3 个 K-Means 性格画像，查看各画像的流派与代表歌手；
2. 按性格标签找歌手 —— 用户自由勾选 26 个性格/生活方式/兴趣标签，
   系统按「标签 → 参考人群 → 流派亲和度 → 歌手」链路实时合成推荐。

数据源：只读取 outputs/tables/ 下已入库的分析结果表（不依赖原始数据），
因此克隆仓库或部署到 Streamlit Community Cloud 后无需重新跑分析、冷启动即可用。
分析逻辑见 src/，完整分析报告见 reports/。
登录认证见 auth.py（凭据存 st.secrets，注册用户持久化到 data/users.json）。

本地运行：
    streamlit run app.py
"""
import json
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from auth import login_gate, resolve_dirs

# 结果表在打包后位于 _MEIPASS 只读资源目录，源码运行时就是项目根目录
RESOURCE_DIR, ROOT = resolve_dirs()
TAB = RESOURCE_DIR / "outputs" / "tables"

st.set_page_config(page_title="性格 × 流行歌手推荐器", page_icon="🎧", layout="wide")

# ---- 登录门禁：未登录会渲染登录/注册页并中断脚本，通过后继续渲染仪表盘 ----
authenticator, user_name, user_name_id = login_gate()


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


# ---------------------------------------------------------------- 侧边栏 ----
with st.sidebar:
    page = st.radio("推荐方式", ["按画像推荐", "按性格标签找歌手"],
                    label_visibility="collapsed")

    if page == "按画像推荐":
        st.header("选择性格画像")
        options = [f"{p}（{demo.loc[p, '人数']} 人）" for p in PROFILES]
        choice = st.radio("画像", options, label_visibility="collapsed")
        profile = PROFILES[options.index(choice)]

    st.divider()
    st.caption(f"当前登录：**{user_name or user_name_id}**")
    authenticator.logout(location="sidebar", button_name="退出登录")

    st.divider()
    st.caption(
        "**项目背景**\n\n"
        "基于 1010 名 15~30 岁年轻人的性格问卷（Kaggle Young People Survey）"
        "与 28356 首 Spotify 歌曲数据，通过 K-Means 聚类把年轻人分成 3 个性格画像，"
        "再结合画像的流派偏好与各流派 Top 歌手给出推荐。\n\n"
        f"画像间流派偏好差异经 Kruskal-Wallis 检验，17 个流派中 15 个显著（p<0.05）。"
    )

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

# ============================================================ 页面1: 画像 ====
if page == "按画像推荐":
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

    # ---- 性格雷达图 + 五维解读 ----
    st.subheader("性格侧写（五维人格代理指标）")
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
    st.subheader("音乐偏好与代表歌手")
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
else:
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
    st.html("""
<style>
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
    import streamlit.components.v1 as components

    components.html("""
<script>
(function () {
  var doc = window.parent.document;
  var tries = 0;
  function setup() {
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
    var remaining = [...doc.querySelectorAll('[data-testid="stButtonGroup"] > div')]
      .filter(function (r) { return r.dataset.navReady !== "1"; }).length;
    if (remaining && tries++ < 25) setTimeout(setup, 300);
  }
  setup();
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
    st.subheader("你的人群画像偏爱哪些流派")
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

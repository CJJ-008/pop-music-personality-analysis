# -*- coding: utf-8 -*-
"""Streamlit 歌手推荐器：什么性格的年轻人喜欢什么样的流行歌手？

数据源：只读取 outputs/tables/ 下已入库的分析结果表（不依赖原始数据），
因此克隆仓库或部署到 Streamlit Community Cloud 后无需重新跑分析、冷启动即可用。
分析逻辑见 src/，完整分析报告见 reports/。
登录认证见 auth.py（凭据存 st.secrets，注册用户持久化到 data/users.json）。

本地运行：
    streamlit run app.py
"""
from pathlib import Path

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
    """读取分析结果表；index_col=True 表示首列是画像名作为行索引。"""
    path = TAB / name
    if not path.exists():
        st.error(f"缺少结果表 outputs/tables/{name}。"
                 f"请先在本地依次运行 src/02~06 分析脚本，并确认 outputs/tables/ 已提交。")
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

PROFILES = demo.index.tolist()

# ---------------------------------------------------------------- 侧边栏 ----
with st.sidebar:
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
        "再结合画像的流派偏好与各流派 Top 歌手，得到本页推荐结论。\n\n"
        f"画像间流派偏好差异经 Kruskal-Wallis 检验，17 个流派中 15 个显著（p<0.05）。"
    )
    st.caption("完整分析报告见仓库 reports/流行音乐数据分析报告.ipynb")

# ---------------------------------------------------------------- 主区域 ----
st.title("🎧 性格 × 流行歌手推荐器")
st.caption("选择左侧的性格画像，查看这类年轻人偏爱的音乐流派与代表歌手")

row = demo.loc[profile]

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
st.caption("流派按「相对全体均值的偏好差异」排序（而非绝对分），才能体现画像的特征偏好")

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

    # 降序排列：排名第 1 = 平均流行度最高；画条形图时再反转，让最高者在图顶部
    top = (artists[artists["Spotify流派"] == genre]
           .sort_values("平均流行度", ascending=False)
           .reset_index(drop=True))
    if top.empty:
        st.warning(f"流派「{genre}」暂无歌手数据")
        continue

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
    st.plotly_chart(fig, width="stretch")

    table = top[["歌手", "歌曲数", "平均流行度"]].copy()
    table.index = table.index + 1
    table.index.name = "排名"
    st.dataframe(table, width="stretch", height=min(420, 35 * len(table) + 38))

    st.markdown(f"**推荐歌手**：{'、'.join(esc(a) for a in top['歌手'].head(5))}")

# ---- 页脚说明 ----
st.divider()
st.caption(
    "**结论口径说明**：两份数据集不是同一批人，通过「流派」桥接，"
    "本页结论是**画像层面的群体倾向**，不是个体因果关系；"
    "「尽责自律·宜人友善型」各流派偏好均衡、无明显特征流派，推荐结果为相对最接近者。"
)

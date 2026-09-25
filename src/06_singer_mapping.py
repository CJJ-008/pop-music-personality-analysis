# -*- coding: utf-8 -*-
"""画像 × 歌手映射：把「性格画像 -> 流派偏好 -> 代表歌手」串成最终结论。

这是回答业务问题的成品脚本。桥接逻辑：
  问卷侧 17 个细流派偏好  ->  映射到 Spotify 侧 6 大流派  ->  该流派 Top 歌手

映射说明（重要，报告中需披露）：
  - 两份数据集不是同一批人，通过「流派」这一共同维度桥接，结论是画像层面的
    群体倾向，不是个体因果；
  - Spotify 数据集只有 6 大流派，问卷里的民谣/乡村/古典/音乐剧/歌剧无对应项，
    这 5 个流派不参与歌手映射（占比会在输出中说明）。

输出：outputs/tables/singer_mapping_*.csv、outputs/figures/fig17_*.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    GENRE_CN, RANDOM_STATE, SPOTIFY_CLEAN_CSV, SURVEY_CLUSTER_CSV,
    save_fig, save_table,
)

np.random.seed(RANDOM_STATE)

# 问卷细流派 -> Spotify 六大流派（近似映射，爵士/雷鬼归入 r&b 是数据集所限）
SURVEY_TO_SPOTIFY = {
    "Pop": "pop",
    "Rock": "rock", "Metal or Hardrock": "rock", "Punk": "rock",
    "Alternative": "rock", "Rock n roll": "rock",
    "Hiphop, Rap": "rap",
    "Dance": "edm", "Techno, Trance": "edm",
    "Latino": "latin",
    "Swing, Jazz": "r&b", "Reggae, Ska": "r&b",
}
# 问卷中有、但 Spotify 数据集无对应流派（不参与歌手映射）
UNMAPPED_CN = ["民谣", "乡村", "古典", "音乐剧", "歌剧"]

MIN_SONGS = 10  # 歌手入选门槛：至少这么多首歌，避免单曲偶然高流行度


def esc(text: str) -> str:
    """转义 $ 符号：matplotlib 会把 $...$ 当 LaTeX 数学公式解析，
    导致歌手名（如 $uicideBoy$）的美元符号被吞掉、字变成斜体。
    """
    return str(text).replace("$", r"\$")


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    survey = pd.read_csv(SURVEY_CLUSTER_CSV)
    spotify = pd.read_csv(SPOTIFY_CLEAN_CSV).drop_duplicates(subset="track_id")
    print(f"[映射] 问卷 {len(survey)} 人（{survey['cluster_name'].nunique()} 个画像），"
          f"Spotify 去重后 {len(spotify)} 首歌")
    return survey, spotify


def top_artists(spotify: pd.DataFrame, genre: str, n: int = 8) -> pd.DataFrame:
    sub = spotify[spotify["playlist_genre"] == genre]
    g = (sub.groupby("track_artist")
            .agg(歌曲数=("track_id", "size"), 平均流行度=("track_popularity", "mean"),
                 最高流行度=("track_popularity", "max"))
            .query("歌曲数 >= @MIN_SONGS")
            .sort_values("平均流行度", ascending=False))
    return g.head(n).round(1)


def main() -> None:
    survey, spotify = load()

    # ---- 1. 每个 Spotify 流派的 Top 歌手 ----
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location(
        "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
    eda = module_from_spec(spec)
    spec.loader.exec_module(eda)

    artist_rows = []
    for genre, cn in GENRE_CN.items():
        top = top_artists(spotify, genre)
        print(f"\n[映射] {cn}({genre}) Top 歌手（歌曲数≥{MIN_SONGS}）:")
        print(top.to_string())
        for rank, (artist, row) in enumerate(top.iterrows(), 1):
            artist_rows.append({"Spotify流派": cn, "排名": rank, "歌手": artist,
                                "歌曲数": int(row["歌曲数"]),
                                "平均流行度": row["平均流行度"]})
    artists_df = pd.DataFrame(artist_rows)
    save_table(artists_df, "singer_top_by_genre.csv")

    # ---- 2. 画像 -> Spotify 流派倾向分 ----
    mapped = {k: v for k, v in SURVEY_TO_SPOTIFY.items() if k in survey.columns}
    pref = survey.groupby("cluster_name")[list(mapped)].mean()
    # 把细流派偏好聚合到 6 大流派（同一 Spotify 流派的多个细流派取均值）
    agg = pref.T.groupby(mapped).mean().T.rename(columns=GENRE_CN)
    print(f"\n[映射] 各画像对 6 大 Spotify 流派的倾向分（1-5）:")
    print(agg.round(2).to_string())
    save_table(agg.round(3), "singer_profile_genre_score.csv", index=True)

    # ---- 3. 核心结论表：画像 -> 偏好流派 -> 代表歌手 ----
    # 用「相对偏好」（该画像倾向分 - 全体均值）排序，而非绝对分：
    # 绝对分下所有画像都以流行乐居首，看不出画像差异；相对偏好才能凸显各画像的特征流派。
    overall = agg.mean()
    agg_rel = agg.sub(overall, axis=1)
    print(f"\n[映射] 各画像相对全体的流派偏好差异:")
    print(agg_rel.round(2).to_string())
    save_table(agg_rel.round(3), "singer_profile_genre_relative.csv", index=True)

    conclusion = []
    for profile, row in agg_rel.iterrows():
        ranked = row.sort_values(ascending=False)
        # 若最强的相对偏好都很小（<0.1），说明该画像口味均衡、没有突出偏好，如实标注
        flat = ranked.iloc[0] < 0.1
        for rank, gcn in enumerate(ranked.index[:2], 1):
            artists = artists_df[artists_df["Spotify流派"] == gcn].head(5)["歌手"].tolist()
            note = ""
            if flat and rank == 1:
                note = "该画像各流派偏好均衡，无明显特征流派，以下为相对最接近者"
            elif flat:
                note = "次选，实际偏好低于全体均值"
            conclusion.append({
                "性格画像": profile,
                "偏好排名": f"第{rank}特征流派",
                "特征流派": gcn,
                "相对偏好": round(row[gcn], 2),
                "绝对倾向分": round(agg.loc[profile, gcn], 2),
                "代表歌手": "、".join(artists),
                "解读提示": note,
            })
    concl = pd.DataFrame(conclusion)
    print("\n[映射] ===== 核心结论：什么性格的年轻人喜欢什么歌手 =====")
    for profile, grp in concl.groupby("性格画像", sort=False):
        print(f"\n  【{profile}】")
        for _, r in grp.iterrows():
            print(f"    {r['偏好排名']}：{r['特征流派']}"
                  f"（相对偏好 {r['相对偏好']:+.2f}，绝对 {r['绝对倾向分']}）"
                  f" -> {r['代表歌手']}")
    save_table(concl, "singer_conclusion_table.csv")

    # ---- 3b. 问卷侧完整流派结论（17 个细流派，含 Spotify 无对应的）----
    survey_genres = [g for g in eda.MUSIC_GENRES if g in survey.columns]
    spref = survey.groupby("cluster_name")[survey_genres].mean()
    spref_rel = spref.sub(survey[survey_genres].mean(), axis=1)
    detail = []
    for profile, row in spref_rel.iterrows():
        for g in row.sort_values(ascending=False).index[:5]:
            detail.append({
                "性格画像": profile,
                "问卷流派": eda.GENRE_CN_SURVEY[g],
                "相对偏好": round(row[g], 2),
                "可映射歌手": "是" if g in SURVEY_TO_SPOTIFY else "否(Spotify无此流派)",
            })
    detail_df = pd.DataFrame(detail)
    print("\n[映射] 各画像在问卷 17 个细流派上最突出的 5 个（含无法映射歌手的流派）:")
    print(detail_df.to_string(index=False))
    save_table(detail_df, "singer_survey_genre_detail.csv")

    # ---- 4. 可视化：画像 × 流派倾向 热力图 ----
    fig, ax = plt.subplots(figsize=(8, 4))
    sns.heatmap(agg, annot=True, fmt=".2f", cmap="YlOrRd", ax=ax,
                annot_kws={"size": 9}, cbar_kws={"label": "倾向分（1-5）"})
    ax.set_title("图17 各性格画像对六大流派的倾向分")
    ax.set_xlabel(""); ax.set_ylabel("")
    save_fig(fig, "fig17_profile_spotify_genre.png")

    # ---- 5. 可视化：每个画像的 Top 歌手 ----
    profiles = concl["性格画像"].unique().tolist()
    # wspace 留足间距：歌手名较长时，y 轴标签会伸到相邻子图区域被遮挡
    fig, axes = plt.subplots(1, len(profiles), figsize=(6.2 * len(profiles), 5.5),
                             gridspec_kw={"wspace": 0.5})
    if len(profiles) == 1:
        axes = [axes]
    for ax, profile in zip(axes, profiles):
        gcn = concl[(concl["性格画像"] == profile) &
                    (concl["偏好排名"] == "第1特征流派")]["特征流派"].iloc[0]
        sub = artists_df[artists_df["Spotify流派"] == gcn].head(6).iloc[::-1]
        ax.barh([esc(a) for a in sub["歌手"]], sub["平均流行度"], color="#4c72b0")
        ax.set_title(f"{profile}\n第1特征流派：{gcn}", fontsize=9)
        ax.set_xlabel("平均流行度")
        ax.tick_params(axis="y", labelsize=8)
    fig.suptitle("图18 各性格画像特征流派的代表歌手 Top6", y=1.02)
    save_fig(fig, "fig18_profile_top_artists.png")

    print(f"\n[映射] 说明：{len(UNMAPPED_CN)} 个问卷流派（{'、'.join(UNMAPPED_CN)}）"
          f"在 Spotify 数据集中无对应项，未参与歌手映射")
    print("[映射] 完成，核心结论表 -> outputs/tables/singer_conclusion_table.csv")


if __name__ == "__main__":
    main()

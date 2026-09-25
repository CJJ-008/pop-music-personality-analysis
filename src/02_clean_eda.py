# -*- coding: utf-8 -*-
"""清洗 + 探索性分析（EDA）：两份原始数据 -> 清洗后数据 + 描述统计表 + 基础图表。

问卷侧（Kaggle Young People Survey，1010 人 × 150 列）：
  - 1-5 分量表题用中位数填补缺失（总缺失仅 0.4%）；
  - 基于大五人格框架，用语义对应题目合成 5 个性格维度得分（代理指标）：
      外向社交 / 尽责自律 / 情绪稳定 / 开放好奇 / 宜人友善
    说明：这是问卷单题合成的人格代理变量，非标准大五量表，报告与面试中如实说明。
歌曲侧（TidyTuesday Spotify Songs，32833 首 × 23 列）：
  - 同一首歌出现在多个歌单会产生重复 track_id，建模用去重后数据；
  - 解析发行年份，统计各流派规模与流行度分布。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    GENRE_CN, RANDOM_STATE, SPOTIFY_CLEAN_CSV, SPOTIFY_CSV, SURVEY_CLEAN_CSV,
    SURVEY_CSV, save_fig, save_table,
)

np.random.seed(RANDOM_STATE)

# ---------------------------------------------------------------- 问卷侧 ----
# 17 个音乐流派打分列（列名与原始数据一致）
MUSIC_GENRES = [
    "Dance", "Folk", "Country", "Classical music", "Musical", "Pop", "Rock",
    "Metal or Hardrock", "Punk", "Hiphop, Rap", "Reggae, Ska", "Swing, Jazz",
    "Rock n roll", "Alternative", "Latino", "Techno, Trance", "Opera",
]
GENRE_CN_SURVEY = {
    "Dance": "舞曲", "Folk": "民谣", "Country": "乡村", "Classical music": "古典",
    "Musical": "音乐剧", "Pop": "流行", "Rock": "摇滚", "Metal or Hardrock": "金属/硬摇",
    "Punk": "朋克", "Hiphop, Rap": "嘻哈/说唱", "Reggae, Ska": "雷鬼", "Swing, Jazz": "爵士",
    "Rock n roll": "摇滚乐", "Alternative": "另类", "Latino": "拉丁", "Techno, Trance": "电音",
    "Opera": "歌剧",
}

# 大五人格代理指标 <- 问卷题目（均为 1-5 分，分值越高越同意）
BIG_FIVE_ITEMS = {
    "外向社交": ["Fun with friends", "Socializing", "Number of friends",
               "Energy levels", "Dancing", "Entertainment spending", "Adrenaline sports"],
    # Punctuality 是文字选项题，先按序数编码为 1-5 分再参与合成（见 ORDINAL_MAPS）
    "尽责自律": ["Reliability", "Keeping promises", "Punctuality", "Prioritising workload",
               "Workaholism", "Thinking ahead", "Writing notes"],
    # 负向题：分值越高情绪越不稳定 -> 反向计分为 情绪稳定
    "情绪稳定": ["Life struggles", "Mood swings", "Getting angry", "Loss of interest",
               "Loneliness", "Hypochondria", "Flying", "Storm", "Darkness", "Heights",
               "Spiders", "Snakes", "Rats", "Ageing", "Dangerous dogs", "Fear of public speaking"],
    "开放好奇": ["Art exhibitions", "Theatre", "Reading", "Foreign languages",
               "Psychology", "Writing", "Musical instruments", "Science and technology"],
    "宜人友善": ["Empathy", "Compassion to animals", "Giving", "Charity",
               "Borrowed stuff", "Friends versus money", "Waiting", "Lying"],
}

# 文字选项题 -> 1-5 分序数编码（问卷中少数量表题是文字选项而非数字打分）
ORDINAL_MAPS = {
    "Punctuality": {"i am often running late": 1, "i am always on time": 3, "i am often early": 5},
    "Lying": {"never": 5, "only to avoid hurting someone": 4, "sometimes": 3,
              "everytime it suits me": 1},  # 分值越高越诚实，可正向计入宜人性
}

DEMO_CATEGORICAL = ["Gender", "Education", "Village - town", "Only child",
                    "Internet usage", "Smoking", "Alcohol"]


def clean_survey() -> pd.DataFrame:
    df = pd.read_csv(SURVEY_CSV)
    print(f"[问卷] 读入 {df.shape[0]} 行 × {df.shape[1]} 列")

    missing = df.isna().sum().sort_values(ascending=False)
    print(f"[问卷] 含缺失的列数: {(missing > 0).sum()}/{df.shape[1]}，"
          f"总缺失率 {df.isna().sum().sum() / df.size:.1%}")
    save_table(missing[missing > 0].rename("缺失数").to_frame(), "survey_missing_top.csv", index=True)

    # 文字选项题先做序数编码，使全部量表题统一为数值型
    for col, mapping in ORDINAL_MAPS.items():
        if col in df.columns:
            df[col] = df[col].map(mapping).astype(float)
            print(f"[问卷] 序数编码: {col} -> 1-5 分")

    # 1-5 分量表题：中位数填补；分类变量：众数填补
    scale_cols = [c for c in MUSIC_GENRES + sum(BIG_FIVE_ITEMS.values(), []) if c in df.columns]
    non_numeric = [c for c in scale_cols if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        # 守住底线：非数值列无法参与均值合成，宁可剔除并告警，也不要静默算错
        print(f"[问卷] 警告: 以下列非数值型，已从量表合成中剔除 -> {non_numeric}")
        scale_cols = [c for c in scale_cols if c not in non_numeric]
    df[scale_cols] = df[scale_cols].fillna(df[scale_cols].median())
    for c in DEMO_CATEGORICAL:
        df[c] = df[c].fillna(df[c].mode()[0])

    # 其余数值列（兴趣爱好等）也统一中位数填补，保证后续聚类/分类脚本拿到干净矩阵
    num_cols = [c for c in df.columns
                if pd.api.types.is_numeric_dtype(df[c]) and c not in scale_cols]
    rest_na = int(df[num_cols].isna().sum().sum())
    if rest_na:
        df[num_cols] = df[num_cols].fillna(df[num_cols].median())
        print(f"[问卷] 其余 {len(num_cols)} 个数值列中位数填补 {rest_na} 个缺失值")
    print(f"[问卷] 填补后剩余缺失值: {int(df.isna().sum().sum())}")

    # 合成大五人格代理指标（情绪稳定 = 6 - 负向题均值，即反向计分到 1-5）
    trait_scores = {}
    for trait, items in BIG_FIVE_ITEMS.items():
        items = [c for c in items if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
        score = df[items].mean(axis=1)
        trait_scores[trait] = 6 - score if trait == "情绪稳定" else score
    df = pd.concat([df, pd.DataFrame(trait_scores, index=df.index)], axis=1)
    traits = list(BIG_FIVE_ITEMS)
    print(f"[问卷] 大五代理指标已合成: {traits}")
    print(df[traits].describe().loc[["mean", "std"]].round(2).to_string())

    save_table(df[traits].describe().round(3), "survey_proxy_describe.csv")
    save_table(df[MUSIC_GENRES].mean().round(3).rename("平均分").to_frame()
               .assign(流派中文=lambda t: [GENRE_CN_SURVEY[i] for i in t.index]),
               "survey_genre_means.csv", index=True)
    print(f"[问卷] 打分最高的流派: {df[MUSIC_GENRES].mean().idxmax()}")

    df.to_csv(SURVEY_CLEAN_CSV, index=False, encoding="utf-8-sig")
    print(f"[问卷] 清洗后数据 -> {SURVEY_CLEAN_CSV.name}")
    return df


def eda_survey(df: pd.DataFrame) -> None:
    traits = list(BIG_FIVE_ITEMS)

    means = df[MUSIC_GENRES].mean().sort_values()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh([GENRE_CN_SURVEY[g] for g in means.index], means.values, color="#4c72b0")
    ax.set_xlabel("平均打分（1-5）")
    ax.set_title("图1 年轻人对 17 个音乐流派的平均偏好打分")
    save_fig(fig, "fig01_survey_genre_means.png")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].hist(df["Age"].dropna(), bins=16, color="#4c72b0", edgecolor="white")
    axes[0].set_title("年龄分布（15~30 岁）"); axes[0].set_xlabel("年龄")
    df["Gender"].value_counts().plot(kind="bar", ax=axes[1], color="#dd8452")
    axes[1].set_title("性别构成"); axes[1].tick_params(axis="x", rotation=0)
    fig.suptitle("图2 受访者人口学概况")
    save_fig(fig, "fig02_survey_age_gender.png")

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(df[traits].corr(), annot=True, fmt=".2f", cmap="RdBu_r",
                vmin=-1, vmax=1, ax=ax, cbar_kws={"label": "相关系数"})
    ax.set_title("图3 五个性格维度的相关性")
    save_fig(fig, "fig03_proxy_corr_heatmap.png")


# ---------------------------------------------------------------- 歌曲侧 ----
AUDIO_FEATURES = ["danceability", "energy", "key", "loudness", "mode", "speechiness",
                  "acousticness", "instrumentalness", "liveness", "valence", "tempo",
                  "duration_ms"]


def clean_spotify() -> pd.DataFrame:
    df = pd.read_csv(SPOTIFY_CSV)
    print(f"\n[Spotify] 读入 {df.shape[0]} 行 × {df.shape[1]} 列")
    print(f"[Spotify] 缺失值总数: {df.isna().sum().sum()}")
    dup = df["track_id"].duplicated().sum()
    print(f"[Spotify] 重复 track_id（同一首歌出现在多个歌单）: {dup} 行")

    df["release_year"] = pd.to_numeric(df["track_album_release_date"].astype(str).str[:4],
                                       errors="coerce")
    df["genre_cn"] = df["playlist_genre"].map(GENRE_CN)

    df.to_csv(SPOTIFY_CLEAN_CSV, index=False, encoding="utf-8-sig")
    print(f"[Spotify] 清洗后数据 -> {SPOTIFY_CLEAN_CSV.name}")
    return df


def eda_spotify(df: pd.DataFrame) -> None:
    summary = (df.groupby("genre_cn")
                 .agg(歌曲数=("track_id", "size"), 去重歌曲数=("track_id", "nunique"),
                      歌手数=("track_artist", "nunique"), 平均流行度=("track_popularity", "mean"))
                 .round(2).sort_values("歌曲数", ascending=False))
    print(f"[Spotify] 各流派规模:\n{summary.to_string()}")
    save_table(summary, "spotify_genre_summary.csv", index=True)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    summary["歌曲数"].plot(kind="bar", ax=ax, color="#4c72b0")
    ax.set_ylabel("歌曲数（按歌单曲目计）"); ax.set_xlabel("")
    ax.set_title("图4 Spotify 六大流派歌曲规模")
    ax.tick_params(axis="x", rotation=0)
    save_fig(fig, "fig04_spotify_genre_counts.png")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(df["track_popularity"], bins=40, color="#55a868", edgecolor="white")
    ax.set_xlabel("歌曲流行度 track_popularity（0-100）"); ax.set_ylabel("歌曲数")
    ax.set_title(f"图5 歌曲流行度分布（中位数 {df['track_popularity'].median():.0f}）")
    save_fig(fig, "fig05_spotify_popularity_hist.png")

    corr_cols = AUDIO_FEATURES + ["track_popularity"]
    fig, ax = plt.subplots(figsize=(9, 7.5))
    sns.heatmap(df[corr_cols].corr(), annot=True, fmt=".2f", cmap="RdBu_r",
                vmin=-1, vmax=1, ax=ax, annot_kws={"size": 8},
                cbar_kws={"label": "相关系数"})
    ax.set_title("图6 音频特征与流行度的相关性矩阵")
    save_fig(fig, "fig06_spotify_audio_corr.png")

    order = summary.index.tolist()
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.boxplot(data=df, x="genre_cn", y="track_popularity", order=order, ax=ax,
                hue="genre_cn", palette="Set2", legend=False)
    ax.set_xlabel(""); ax.set_ylabel("流行度")
    ax.set_title("图7 各流派歌曲流行度分布")
    save_fig(fig, "fig07_spotify_pop_by_genre_box.png")

    top_overall = (df.groupby("track_artist")["track_popularity"]
                     .agg(["mean", "size"]).query("size >= 15")
                     .sort_values("mean", ascending=False).head(10))
    print("[Spotify] 歌曲数≥15 的平均流行度 Top10 歌手:")
    print(top_overall.round(1).to_string())


if __name__ == "__main__":
    survey = clean_survey()
    eda_survey(survey)
    spotify = clean_spotify()
    eda_spotify(spotify)
    print("\n[完成] 清洗与 EDA 输出见 outputs/ 与 data/processed/")

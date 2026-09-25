# -*- coding: utf-8 -*-
"""性格聚类：把 1010 名年轻人按大五人格代理指标聚成若干「性格画像」。

流程：
  1. 标准化 5 个性格维度 -> K-Means 聚类；
  2. 用肘部法则（inertia）与轮廓系数确定最佳 K（2~10）；
  3. 层次聚类（Ward 连接）作对比，用调整兰德指数 ARI 衡量两种算法一致性；
  4. PCA 降到二维可视化聚类结果；
  5. 依据各簇的性格 z-score 峰值自动命名画像；
  6. 输出「画像 × 音乐流派偏好」矩阵与热力图 —— 这是回答业务问题的核心中间产物。

输出：data/processed/survey_with_cluster.csv、outputs/figures/fig1x_*.png、outputs/tables/*.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    RANDOM_STATE, SURVEY_CLEAN_CSV, SURVEY_CLUSTER_CSV, save_fig, save_table,
)

np.random.seed(RANDOM_STATE)

TRAITS = ["外向社交", "尽责自律", "情绪稳定", "开放好奇", "宜人友善"]
K_RANGE = range(2, 11)


def load_eda_module():
    """按文件路径加载 02_clean_eda.py（模块名以数字开头，无法用常规 import）。"""
    import importlib.util

    path = Path(__file__).resolve().parent / "02_clean_eda.py"
    spec = importlib.util.spec_from_file_location("eda_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_features() -> tuple[pd.DataFrame, np.ndarray, StandardScaler]:
    df = pd.read_csv(SURVEY_CLEAN_CSV)
    scaler = StandardScaler()
    X = scaler.fit_transform(df[TRAITS])
    print(f"[聚类] 样本 {X.shape[0]} 人，特征 {X.shape[1]} 个性格维度")
    return df, X, scaler


def choose_k(X: np.ndarray) -> tuple[int, pd.DataFrame]:
    """定 K 规则：肘部法则看趋势，轮廓系数定候选，再取「轮廓系数 ≥ 最优值 90%」中最大的 K。

    实测本数据所有 K 的轮廓系数均 < 0.2，说明年轻人性格不存在泾渭分明的分群
    （真实人格数据普遍如此）。若直接取轮廓系数最大的 K=2，画像过于粗糙、
    不具业务价值，因此在可接受的质量损失内选择更细的划分，并在报告中如实披露。
    """
    rows = []
    for k in K_RANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE)
        labels = km.fit_predict(X)
        rows.append({"K": k, "inertia": km.inertia_,
                     "silhouette": silhouette_score(X, labels)})
    scores = pd.DataFrame(rows).set_index("K")
    best_sil = scores["silhouette"].max()
    threshold = 0.9 * best_sil
    best_k = int(scores[scores["silhouette"] >= threshold].index.max())
    print(f"[聚类] 各 K 的轮廓系数:\n{scores.round(3).to_string()}")
    print(f"[聚类] 轮廓系数最优 {best_sil:.3f}（K={int(scores['silhouette'].idxmax())}）；"
          f"取 ≥90% 最优值的最大 K -> K={best_k}（{scores.loc[best_k, 'silhouette']:.3f}）")
    save_table(scores.round(4), "cluster_k_selection.csv", index=True)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(scores.index, scores["inertia"], "o-", color="#4c72b0")
    axes[0].set_xlabel("聚类数 K"); axes[0].set_ylabel("簇内平方和 inertia")
    axes[0].set_title("肘部法则")
    axes[1].plot(scores.index, scores["silhouette"], "o-", color="#dd8452")
    axes[1].axvline(best_k, ls="--", c="gray", lw=1)
    axes[1].set_xlabel("聚类数 K"); axes[1].set_ylabel("轮廓系数")
    axes[1].set_title(f"轮廓系数（最优 K={best_k}）")
    fig.suptitle("图8 聚类数 K 的选取")
    save_fig(fig, "fig08_cluster_k_selection.png")
    return best_k, scores


def name_profiles(df: pd.DataFrame, labels: np.ndarray) -> dict[int, str]:
    """按各簇性格 z-score 最高的两个维度自动命名画像。"""
    z = (df[TRAITS] - df[TRAITS].mean()) / df[TRAITS].std()
    z = z.assign(cluster=labels)
    means = z.groupby("cluster")[TRAITS].mean()
    names = {}
    for cid, row in means.iterrows():
        top2 = row.sort_values(ascending=False).index[:2].tolist()
        names[int(cid)] = "·".join(top2) + "型"
    # 处理重名：重名的簇追加次要维度区分
    seen: dict[str, int] = {}
    for cid in sorted(names):
        base = names[cid]
        if base in seen:
            row = means.loc[cid]
            third = row.sort_values(ascending=False).index[2]
            names[cid] = f"{base[:-1]}(偏{third})型"
        seen[names[cid]] = cid
    return names


def main() -> None:
    df, X, scaler = load_features()
    best_k, _ = choose_k(X)

    km = KMeans(n_clusters=best_k, n_init=10, random_state=RANDOM_STATE)
    km_labels = km.fit_predict(X)
    print(f"[聚类] K-Means 完成，各簇人数: {np.bincount(km_labels).tolist()}")

    # 层次聚类对比（Ward 最小方差连接）
    hc = AgglomerativeClustering(n_clusters=best_k, linkage="ward")
    hc_labels = hc.fit_predict(X)
    ari = adjusted_rand_score(km_labels, hc_labels)
    print(f"[聚类] 层次聚类对比：与 K-Means 的 ARI = {ari:.3f}（越接近 1 越一致）")

    names = name_profiles(df, km_labels)
    df["cluster"] = km_labels
    df["cluster_name"] = df["cluster"].map(names)
    print("[聚类] 性格画像命名:")
    for cid, nm in names.items():
        n = int((km_labels == cid).sum())
        print(f"    簇{cid} -> {nm}（{n} 人，{n / len(df):.1%}）")

    # ---- PCA 二维可视化 ----
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    coords = pca.fit_transform(X)
    evr = pca.explained_variance_ratio_
    fig, ax = plt.subplots(figsize=(8, 6))
    palette = sns.color_palette("Set2", best_k)
    for cid in range(best_k):
        m = km_labels == cid
        ax.scatter(coords[m, 0], coords[m, 1], s=18, alpha=0.7,
                   color=palette[cid], label=f"{names[cid]} (n={m.sum()})")
    ax.set_xlabel(f"主成分1（解释方差 {evr[0]:.1%}）")
    ax.set_ylabel(f"主成分2（解释方差 {evr[1]:.1%}）")
    ax.set_title(f"图9 性格画像聚类结果（PCA 二维投影，K={best_k}）")
    ax.legend(fontsize=8, loc="best")
    save_fig(fig, "fig09_cluster_pca.png")

    # ---- 画像性格雷达/热力图 ----
    z = (df[TRAITS] - df[TRAITS].mean()) / df[TRAITS].std()
    profile_z = z.assign(cluster_name=df["cluster_name"]).groupby("cluster_name")[TRAITS].mean()
    fig, ax = plt.subplots(figsize=(8, 4.5))
    sns.heatmap(profile_z, annot=True, fmt=".2f", cmap="RdBu_r", center=0,
                ax=ax, cbar_kws={"label": "z-score（相对全体）"})
    ax.set_title("图10 各性格画像的性格维度 z-score")
    ax.set_xlabel("")
    save_fig(fig, "fig10_profile_traits.png")
    save_table(profile_z.round(3), "profile_traits_zscore.csv", index=True)

    # ---- 画像 × 音乐流派偏好（核心产物）----
    eda = load_eda_module()
    genres = [g for g in eda.MUSIC_GENRES if g in df.columns]
    cn = {g: eda.GENRE_CN_SURVEY[g] for g in genres}
    pref = df.groupby("cluster_name")[genres].mean().rename(columns=cn)
    print("\n[聚类] 各画像的流派偏好均值（1-5）:")
    print(pref.round(2).to_string())
    save_table(pref.round(3), "profile_genre_preference.csv", index=True)

    # 减去全体均值，凸显「相对偏好」，避免只看绝对分
    overall = df[genres].mean().rename(index=cn)
    pref_rel = pref.sub(overall, axis=1)
    fig, ax = plt.subplots(figsize=(12, 4.5))
    sns.heatmap(pref_rel, annot=True, fmt=".2f", cmap="RdBu_r", center=0,
                ax=ax, annot_kws={"size": 8}, cbar_kws={"label": "相对全体的偏好差异"})
    ax.set_title("图11 各性格画像的流派相对偏好（红=高于平均，蓝=低于平均）")
    ax.set_xlabel(""); ax.set_ylabel("")
    save_fig(fig, "fig11_profile_genre_heatmap.png")
    save_table(pref_rel.round(3), "profile_genre_relative.csv", index=True)

    # 各画像最爱/最不爱的流派
    fav = pd.DataFrame({
        "最爱流派": pref_rel.idxmax(axis=1),
        "偏好超出均值": pref_rel.max(axis=1).round(2),
        "最不爱流派": pref_rel.idxmin(axis=1),
        "低于均值": pref_rel.min(axis=1).round(2),
        "人数": df["cluster_name"].value_counts(),
    })
    print("\n[聚类] 各画像的流派偏好极值:")
    print(fav.to_string())
    save_table(fav, "profile_favorite_genre.csv", index=True)

    # ---- 显著性检验：画像之间的流派偏好差异是真实的还是随机波动？----
    # Kruskal-Wallis 非参数检验（不假设正态分布，适合 1-5 有序打分）
    from scipy.stats import kruskal

    sig_rows = []
    for g in genres:
        groups = [df.loc[df["cluster_name"] == nm, g].values for nm in pref.index]
        stat, p = kruskal(*groups)
        sig_rows.append({"流派": cn[g], "H统计量": stat, "p值": p,
                         "显著(p<0.05)": "是" if p < 0.05 else "否"})
    sig = pd.DataFrame(sig_rows).sort_values("p值").reset_index(drop=True)
    print("\n[聚类] 画像间流派偏好差异的 Kruskal-Wallis 检验（按 p 值排序）:")
    print(sig.round(4).to_string(index=False))
    n_sig = int((sig["p值"] < 0.05).sum())
    print(f"[聚类] {n_sig}/{len(genres)} 个流派的画像间差异在 0.05 水平上显著")
    save_table(sig.round(6), "profile_genre_kruskal.csv")

    # 只保留显著的流派重画热力图，避免把噪声当结论
    sig_genres = sig.loc[sig["p值"] < 0.05, "流派"].tolist()
    if sig_genres:
        fig, ax = plt.subplots(figsize=(max(6, 1.1 * len(sig_genres)), 4))
        sns.heatmap(pref_rel[sig_genres], annot=True, fmt=".2f", cmap="RdBu_r", center=0,
                    ax=ax, annot_kws={"size": 9}, cbar_kws={"label": "相对全体的偏好差异"})
        ax.set_title("图12 画像间差异显著的流派偏好（Kruskal-Wallis p<0.05）")
        ax.set_xlabel(""); ax.set_ylabel("")
        save_fig(fig, "fig12_profile_genre_significant.png")

    # ---- 画像的人口学画像 ----
    demo = df.groupby("cluster_name").agg(
        人数=("cluster", "size"),
        平均年龄=("Age", "mean"),
        女性占比=("Gender", lambda s: (s == "female").mean()),
        城市占比=("Village - town", lambda s: (s == "city").mean()),
    ).round(2)
    print("\n[聚类] 各画像人口学特征:")
    print(demo.to_string())
    save_table(demo, "profile_demographics.csv", index=True)

    df.to_csv(SURVEY_CLUSTER_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[聚类] 带画像标签的数据 -> {SURVEY_CLUSTER_CSV.name}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""推荐效果离线评测：回答「这套推荐到底有多准」。

方法：留一法（leave-one-out）
  对 1010 名受访者逐个评测——把性格当作输入，**排除他本人**后从其余人中
  找出最相似的 101 人（KNN）或用其所属画像（KMeans），预测他的流派偏好。

为什么不用简单的"命中率@3"作为唯一指标（这是本脚本的一个关键设计决定）：
  实测发现 **73.5% 的受访者"最爱流派"存在并列**（多个流派同分）。
  若把并列流派都算可接受答案，答案集合会变得很大，指标严重虚高，
  且会天然奖励"直接推荐最流行流派"这种策略。因此本脚本采用三个更严格的指标：

  指标1 平均排名：真实最爱流派在预测排序中的平均名次（17 个流派里排第几），
        随机猜的期望约 9.0，越小越好——不受并列影响。
  指标2 斯皮尔曼相关系数：预测的流派亲和度向量与受访者真实打分向量的秩相关，
        衡量"是否预测对了偏好的整体形状"，而不只是猜中第一名。
  指标3 严格命中率：只在"最爱流派唯一"的 268 人子集上算命中率@1/@3，
        彻底排除并列带来的虚高。

同时给出两个基线（随机猜 / 直接推荐最流行的流派），
用来判断"性格到底有没有带来额外信息"——这是评测中最容易被忽略的一步。

运行：python src/10_recommender_eval.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RANDOM_STATE, save_fig, save_table  # noqa: E402
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402

spec = spec_from_file_location(
    "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
eda = module_from_spec(spec)
spec.loader.exec_module(eda)

ROOT = Path(__file__).resolve().parents[1]
SURVEY_CLUSTER = ROOT / "data" / "processed" / "survey_with_cluster.csv"

K_TOP = 101
TOP_N = 3
N_RANDOM_TRIALS = 200

QUIZ_TRAITS = ["外向社交", "尽责自律", "情绪稳定", "开放好奇", "宜人友善"]
QUIZ_ITEMS = {
    "外向社交": [("Fun with friends", 0), ("Socializing", 0), ("Number of friends", 0),
             ("Energy levels", 0), ("Dancing", 0)],
    "尽责自律": [("Reliability", 0), ("Keeping promises", 0), ("Punctuality", 0),
             ("Prioritising workload", 0), ("Workaholism", 0)],
    "情绪稳定": [("Mood swings", 1), ("Getting angry", 1), ("Loneliness", 1),
             ("Hypochondria", 1), ("Life struggles", 1)],
    "开放好奇": [("Reading", 0), ("Foreign languages", 0), ("Art exhibitions", 0),
             ("Psychology", 0), ("Science and technology", 0)],
    "宜人友善": [("Empathy", 0), ("Compassion to animals", 0), ("Giving", 0),
             ("Charity", 0), ("Borrowed stuff", 0)],
}


def main() -> None:
    df = pd.read_csv(SURVEY_CLUSTER)
    genres = [g for g in eda.MUSIC_GENRES if g in df.columns]
    n = len(df)
    print(f"[评测] 受访者 {n} 人，流派 {len(genres)} 个，KNN k={K_TOP}")

    # ---- 性格矩阵（25 题口径，与测评页一致）----
    trait = {}
    for t in QUIZ_TRAITS:
        parts = [6 - pd.to_numeric(df[c], errors="coerce") if rev
                 else pd.to_numeric(df[c], errors="coerce")
                 for c, rev in QUIZ_ITEMS[t]]
        trait[t] = pd.concat(parts, axis=1).mean(axis=1)
    trait_df = pd.DataFrame(trait)
    z = ((trait_df - trait_df.mean()) / trait_df.std()).to_numpy()

    ratings = df[genres].to_numpy(dtype=float)
    overall = ratings.mean(axis=0)
    max_rating = ratings.max(axis=1)
    acceptable = [set(np.flatnonzero(ratings[i] >= max_rating[i] - 1e-9)) for i in range(n)]
    unique_fav = np.array([len(a) == 1 for a in acceptable])
    print(f"[评测] 最爱流派唯一者 {unique_fav.sum()} 人，存在并列者 "
          f"{n - unique_fav.sum()} 人（{(n - unique_fav.sum()) / n:.1%}）"
          f"——并列比例高是采用多指标评估的原因")

    # ---- 方法一：KNN 最近邻（排除本人）----
    pred_knn = np.zeros((n, len(genres)))
    for i in range(n):
        dist = np.sqrt(((z - z[i]) ** 2).sum(axis=1))
        dist[i] = np.inf  # 排除本人，避免自我命中造成虚高
        cohort = np.argpartition(dist, K_TOP)[:K_TOP]
        pred_knn[i] = ratings[cohort].mean(axis=0) - overall

    # ---- 方法二：KMeans 画像（排除本人）----
    clusters = df["cluster"].to_numpy()
    pred_prof = np.zeros((n, len(genres)))
    for i in range(n):
        mask = clusters == clusters[i]
        mask[i] = False
        pred_prof[i] = ratings[mask].mean(axis=0) - overall

    # ---- 基线：全体最流行流派（多数类，留一计算避免自身贡献）----
    fav_counts = np.zeros(len(genres))
    for i in range(n):
        for g in acceptable[i]:
            fav_counts[g] += 1 / len(acceptable[i])
    prior = np.zeros((n, len(genres)))
    for i in range(n):
        c = fav_counts.copy()
        for g in acceptable[i]:          # 减去本人的贡献
            c[g] -= 1 / len(acceptable[i])
        prior[i] = c / c.sum()
    pred_major = prior

    # ---- 方法三：混合推荐（性格信号 + 流行度先验）----
    # 动机：上面两个方法各有一半道理——性格携带真实信号（排名优于随机），
    # 但"大众最爱"这个先验更强。那就把两者加权融合，看能否同时超过双方。
    def zscore_rows(mat):
        return (mat - mat.mean(axis=1, keepdims=True)) / (mat.std(axis=1, keepdims=True) + 1e-12)

    aff_z, prior_z = zscore_rows(pred_knn), zscore_rows(prior)

    def mean_rank_on(pred, idx):
        ranks = []
        for i in idx:
            order = np.argsort(-pred[i])
            pos = {g: r + 1 for r, g in enumerate(order)}
            ranks.append(min(pos[g] for g in acceptable[i]))
        return float(np.mean(ranks))

    # 权重 α 在 A 半调参、在 B 半报结果，避免"在评测集上调参"这种自欺做法
    rng_split = np.random.default_rng(RANDOM_STATE)
    perm = rng_split.permutation(n)
    A, B = perm[: n // 2], perm[n // 2:]
    alphas = np.round(np.arange(0, 1.01, 0.1), 2)
    ranks_A = [mean_rank_on(a * aff_z + (1 - a) * prior_z, A) for a in alphas]
    best_alpha = float(alphas[int(np.argmin(ranks_A))])
    pred_hybrid = best_alpha * aff_z + (1 - best_alpha) * prior_z
    print(f"\n[评测] 混合推荐权重 α={best_alpha}（在 A 半 {len(A)} 人上调参，"
          f"在 B 半 {len(B)} 人上验证）")
    print("       α 扫描（A 半平均排名）: "
          + ", ".join(f"{a}:{r:.2f}" for a, r in zip(alphas, ranks_A)))

    def mean_rank(pred):
        """真实最爱流派在预测排序中的平均名次（越小越好）。"""
        return mean_rank_on(pred, np.arange(n))

    def hit_rate(pred, subset, top):
        """严格命中率：只在指定子集上统计，命中=最爱流派落在预测 Top-N 内。"""
        idx = np.flatnonzero(subset)
        hits = 0
        for i in idx:
            top_g = set(np.argsort(-pred[i])[:top])
            if top_g & acceptable[i]:
                hits += 1
        return hits / len(idx)

    def mean_spearman(pred):
        """预测亲和度向量与真实打分向量的秩相关，衡量偏好形状是否预测正确。"""
        vals = []
        for i in range(n):
            rho, _ = spearmanr(pred[i], ratings[i])
            if not np.isnan(rho):
                vals.append(rho)
        return float(np.mean(vals))

    # ---- 随机基线 ----
    rng = np.random.default_rng(RANDOM_STATE)
    rand_pred = rng.random((n, len(genres)))
    rand_rank = mean_rank(rand_pred)
    rand_spearman = 0.0  # 随机向量与真实偏好的秩相关期望为 0

    rows = []
    for name, pred in (("随机猜（基线）", rand_pred),
                       ("多数类猜（基线）", pred_major),
                       ("KMeans 画像", pred_prof),
                       ("KNN 最近邻（测评页）", pred_knn),
                       (f"混合推荐（α={best_alpha}）", pred_hybrid)):
        rows.append({
            "方法": name,
            "平均排名↓": round(mean_rank(pred), 2),
            "斯皮尔曼相关↑": round(mean_spearman(pred), 4),
            "严格命中率@1↑": round(hit_rate(pred, unique_fav, 1), 4),
            "严格命中率@3↑": round(hit_rate(pred, unique_fav, 3), 4),
            "B半平均排名↓": round(mean_rank_on(pred, B), 2),
        })
    res = pd.DataFrame(rows)
    print("\n[评测] ===== 推荐效果对比（留一法，排除本人）=====")
    print(res.to_string(index=False))
    print(f"\n[评测] 注：平均排名满分 {len(genres)}（随机期望 "
          f"{(len(genres) + 1) / 2:.1f}）；严格命中率只在最爱流派唯一的 "
          f"{unique_fav.sum()} 人上统计")
    save_table(res, "recommender_eval.csv")

    # ---- 图表 ----
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    names = res["方法"].tolist()

    axes[0].bar(names, res["平均排名↓"], color="#4c72b0")
    axes[0].axhline((len(genres) + 1) / 2, color="#c44e52", ls="--",
                    label=f"随机期望 {(len(genres) + 1) / 2:.1f}")
    axes[0].set_ylabel("真实最爱流派的平均排名（越小越好）")
    axes[0].set_title("指标1 平均排名")
    axes[0].legend(fontsize=8)
    for xi, v in enumerate(res["平均排名↓"]):
        axes[0].text(xi, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)

    axes[1].bar(names, res["斯皮尔曼相关↑"], color="#55a868")
    axes[1].axhline(0, color="gray", lw=1)
    axes[1].set_ylabel("预测与真实偏好的秩相关")
    axes[1].set_title("指标2 斯皮尔曼相关（偏好形状）")
    for xi, v in enumerate(res["斯皮尔曼相关↑"]):
        axes[1].text(xi, v, f"{v:.3f}", ha="center",
                     va="bottom" if v >= 0 else "top", fontsize=8)

    x = np.arange(len(res)); w = 0.38
    axes[2].bar(x - w / 2, res["严格命中率@1↑"], w, label="@1", color="#4c72b0")
    axes[2].bar(x + w / 2, res["严格命中率@3↑"], w, label="@3", color="#dd8452")
    axes[2].set_xticks(x); axes[2].set_xticklabels(names, rotation=15, ha="right", fontsize=8)
    axes[2].set_ylabel("命中率"); axes[2].legend(fontsize=8)
    axes[2].set_title(f"指标3 严格命中率（唯一最爱 {unique_fav.sum()} 人）")

    for ax in axes:
        ax.tick_params(axis="x", labelsize=8)
    fig.suptitle("图19 推荐效果离线评测：性格到底带来了多少信息")
    fig.tight_layout()
    save_fig(fig, "fig19_recommender_eval.png")

    knn_row = res[res["方法"].str.startswith("KNN")].iloc[0]
    maj_row = res[res["方法"].str.startswith("多数类")].iloc[0]
    print(f"\n[评测] KNN 平均排名 {knn_row['平均排名↓']}（随机期望 "
          f"{(len(genres) + 1) / 2:.1f}），斯皮尔曼相关 {knn_row['斯皮尔曼相关↑']}")
    print(f"[评测] 与多数类基线对比：严格命中率@3 "
          f"KNN {knn_row['严格命中率@3↑']:.1%} vs 多数类 {maj_row['严格命中率@3↑']:.1%}")
    print("[评测] 已保存 recommender_eval.csv 与 fig19_recommender_eval.png")


if __name__ == "__main__":
    main()

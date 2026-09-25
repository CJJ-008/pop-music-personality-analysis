# -*- coding: utf-8 -*-
"""流行度回归：用音频特征与流派预测歌曲流行度 track_popularity，回答「什么样的歌容易火」。

方法要点：
  - **按 track_id 去重**：同一首歌出现在多个歌单会产生重复行，若不去重，
    同一首歌会同时落进训练集与测试集，造成信息泄漏、虚高 R²；
  - 对比线性回归（可解释基线）与随机森林回归（非线性）；
  - 5 折交叉验证报告 R²、RMSE、MAE；
  - 消融对比：仅音频特征 vs 音频特征+流派，量化「流派」带来的增益；
  - 输出特征重要性，翻译成业务语言（舞蹈性/能量/情绪等如何影响走红）。

输出：outputs/tables/regress_*.csv、outputs/figures/fig1x_*.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    GENRE_CN, RANDOM_STATE, SPOTIFY_CLEAN_CSV, save_fig, save_table,
)

np.random.seed(RANDOM_STATE)

AUDIO_FEATURES = ["danceability", "energy", "key", "loudness", "mode", "speechiness",
                  "acousticness", "instrumentalness", "liveness", "valence", "tempo",
                  "duration_ms"]
TARGET = "track_popularity"


def load_data() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(SPOTIFY_CLEAN_CSV)
    n0 = len(df)
    # 关键：按 track_id 去重，避免同一首歌跨训练/测试集造成信息泄漏
    df = df.drop_duplicates(subset="track_id").reset_index(drop=True)
    df = df.dropna(subset=[TARGET])
    df["release_year"] = df["release_year"].fillna(df["release_year"].median())
    print(f"[回归] 原始 {n0} 行 -> 按 track_id 去重后 {len(df)} 行（唯一歌曲）")
    print(f"[回归] 目标 {TARGET}: 均值 {df[TARGET].mean():.1f}，"
          f"中位数 {df[TARGET].median():.0f}，标准差 {df[TARGET].std():.1f}")

    genre_dummies = pd.get_dummies(df["playlist_genre"], prefix="genre").astype(int)
    feats = AUDIO_FEATURES + ["release_year"]
    X = pd.concat([df[feats], genre_dummies], axis=1)
    print(f"[回归] 特征矩阵 {X.shape[0]} 行 × {X.shape[1]} 列"
          f"（音频+年份 {len(feats)}，流派独热 {genre_dummies.shape[1]}）")
    return X.assign(**{TARGET: df[TARGET]}), genre_dummies.columns.tolist()


def cv_metrics(model, X: pd.DataFrame, y: pd.Series, name: str) -> dict:
    cv = KFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    pred = cross_val_predict(model, X, y, cv=cv, n_jobs=-1)
    res = {
        "模型": name,
        "R2": r2_score(y, pred),
        "RMSE": float(np.sqrt(mean_squared_error(y, pred))),
        "MAE": mean_absolute_error(y, pred),
    }
    print(f"[回归] {name}: R²={res['R2']:.4f}, RMSE={res['RMSE']:.2f}, MAE={res['MAE']:.2f}")
    return res, pred


def main() -> None:
    data, genre_cols = load_data()
    y = data[TARGET]
    X_all = data.drop(columns=[TARGET])
    X_audio = X_all[AUDIO_FEATURES + ["release_year"]]

    print("\n[回归] ===== 消融对比：音频特征 vs 加入流派 =====")
    rows = []
    for feats_name, X in (("仅音频+年份", X_audio), ("音频+年份+流派", X_all)):
        for model_name, model in (("线性回归", LinearRegression()),
                                  ("随机森林", RandomForestRegressor(
                                      n_estimators=300, min_samples_leaf=5,
                                      random_state=RANDOM_STATE, n_jobs=-1))):
            res, _ = cv_metrics(model, X, y, f"{model_name}({feats_name})")
            res["特征集"] = feats_name
            rows.append(res)

    results = pd.DataFrame(rows)[["模型", "特征集", "R2", "RMSE", "MAE"]]
    results[["R2", "RMSE", "MAE"]] = results[["R2", "RMSE", "MAE"]].round(4)
    print("\n[回归] 模型对比汇总:")
    print(results.to_string(index=False))
    save_table(results, "regress_model_comparison.csv")

    # 最佳模型 = 全特征随机森林，画预测散点 + 特征重要性
    best_model = RandomForestRegressor(n_estimators=300, min_samples_leaf=5,
                                       random_state=RANDOM_STATE, n_jobs=-1)
    _, pred = cv_metrics(best_model, X_all, y, "随机森林(全特征)")

    fig, ax = plt.subplots(figsize=(6.5, 6))
    ax.scatter(y, pred, s=4, alpha=0.25, color="#4c72b0")
    lims = [0, 100]
    ax.plot(lims, lims, "r--", lw=1.2, label="完美预测线")
    ax.set_xlabel("真实流行度"); ax.set_ylabel("预测流行度")
    ax.set_title(f"图15 随机森林流行度预测（5折CV，R²={r2_score(y, pred):.3f}）")
    ax.legend()
    save_fig(fig, "fig15_regress_pred_scatter.png")

    best_model.fit(X_all, y)
    imp = pd.Series(best_model.feature_importances_,
                    index=X_all.columns).sort_values(ascending=False)
    top = imp.head(15)
    name_cn = {**GENRE_CN, "release_year": "发行年份"}
    label = [name_cn.get(i, i.replace("genre_", "流派:")) for i in top.index]
    save_table(top.round(5).rename("重要性").to_frame(), "regress_feature_importance.csv", index=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(label[::-1], top.values[::-1], color="#c44e52")
    ax.set_xlabel("随机森林特征重要性（不纯度下降）")
    ax.set_title("图16 影响歌曲流行度的最重要因素 Top15")
    save_fig(fig, "fig16_regress_importance.png")
    print("\n[回归] 影响流行度的最重要因素 Top10:")
    print(pd.Series(top.head(10).values, index=label[:10]).round(4).to_string())

    # 相关系数（线性视角，便于业务解读）
    corr = data[AUDIO_FEATURES + [TARGET]].corr()[TARGET].drop(TARGET).sort_values()
    save_table(corr.round(4).rename("与流行度相关系数").to_frame(), "regress_corr.csv", index=True)
    print("\n[回归] 音频特征与流行度的相关系数（升序）:")
    print(corr.round(3).to_string())


if __name__ == "__main__":
    main()

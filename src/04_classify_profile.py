# -*- coding: utf-8 -*-
"""画像分类：用人口学特征与兴趣爱好预测年轻人属于哪个性格画像。

业务含义：拿到一个新用户的年龄、性别、学历、上网时长、兴趣爱好等易得信息，
就能预测其性格画像，进而推荐该画像偏爱的流派与歌手 —— 一个可落地的推荐前置环节。

方法要点（避免循环论证）：
  - 特征**不含** 5 个性格维度本身（画像正是由它们聚类而来，用了就是答案泄漏）；
  - 特征**不含** 17 个音乐流派打分（音乐口味是我们要预测的结果，不能当输入）；
  - 对比 3 个模型：逻辑回归（需标准化）/ 决策树 / 随机森林；
  - 5 折分层交叉验证，报告准确率、宏平均 F1，并与「全猜最多类」的基线对比。

输出：outputs/tables/classify_*.csv、outputs/figures/fig1x_*.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, f1_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RANDOM_STATE, SURVEY_CLUSTER_CSV, save_fig, save_table  # noqa: E402

np.random.seed(RANDOM_STATE)

# 人口学 + 生活方式特征（均为易得信息）
DEMO_FEATURES = ["Age", "Number of siblings", "Height", "Weight"]

# 兴趣爱好/关注领域（非音乐、非性格题）
HOBBY_FEATURES = [
    "Movies", "Horror", "Thriller", "Comedy", "Romantic", "Sci-fi", "Fantasy/Fairy tales",
    "Animated", "Documentary", "Western", "Action", "History", "Psychology", "Politics",
    "Mathematics", "Physics", "Internet", "PC", "Economy Management", "Biology", "Chemistry",
    "Reading", "Geography", "Foreign languages", "Medicine", "Law", "Cars", "Art exhibitions",
    "Religion", "Countryside, outdoors", "Dancing", "Musical instruments", "Writing",
    "Passive sport", "Active sport", "Gardening", "Celebrities", "Shopping",
    "Science and technology", "Theatre", "Fun with friends", "Adrenaline sports", "Pets",
    "Cheating in school", "Health", "God", "Dreams", "Charity",
]

# 分类变量：独热编码后进入模型
CAT_FEATURES = ["Gender", "Education", "Village - town", "Only child",
                "Internet usage", "Smoking", "Alcohol"]


def build_dataset() -> tuple[pd.DataFrame, pd.Series, list[str]]:
    df = pd.read_csv(SURVEY_CLUSTER_CSV)
    num_feats = [c for c in DEMO_FEATURES + HOBBY_FEATURES if c in df.columns]
    cat_feats = [c for c in CAT_FEATURES if c in df.columns]
    X = pd.concat([df[num_feats], pd.get_dummies(df[cat_feats], drop_first=True)], axis=1)
    y = df["cluster_name"]
    print(f"[分类] 特征矩阵 {X.shape[0]} 行 × {X.shape[1]} 列"
          f"（数值 {len(num_feats)} + 独热 {X.shape[1] - len(num_feats)}）")
    print(f"[分类] 目标类别分布:\n{y.value_counts().to_string()}")
    return X, y, num_feats


def evaluate(models: dict, X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    baseline = y.value_counts(normalize=True).max()
    print(f"[分类] 基线（全猜最多类）准确率 = {baseline:.3f}")

    rows, preds = [], {}
    for name, model in models.items():
        y_pred = cross_val_predict(model, X, y, cv=cv)
        preds[name] = y_pred
        rows.append({
            "模型": name,
            "准确率": accuracy_score(y, y_pred),
            "宏平均F1": f1_score(y, y_pred, average="macro"),
        })
        print(f"[分类] {name}: 准确率 {rows[-1]['准确率']:.3f}, 宏平均F1 {rows[-1]['宏平均F1']:.3f}")

    res = pd.DataFrame(rows).sort_values("准确率", ascending=False).reset_index(drop=True)
    res["相对基线提升"] = (res["准确率"] - baseline).round(3)
    save_table(res.round(4), "classify_model_comparison.csv")
    return res, preds, baseline


def plot_confusion(y: pd.Series, y_pred: np.ndarray, name: str) -> None:
    labels = sorted(y.unique())
    cm = confusion_matrix(y, y_pred, labels=labels)
    cm_pct = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(7.5, 6))
    sns.heatmap(cm_pct, annot=True, fmt=".2f", cmap="Blues", ax=ax,
                xticklabels=labels, yticklabels=labels, vmin=0, vmax=1,
                cbar_kws={"label": "行归一化比例"})
    ax.set_xlabel("预测画像"); ax.set_ylabel("真实画像")
    ax.set_title(f"图13 最佳模型（{name}）混淆矩阵")
    plt.setp(ax.get_xticklabels(), rotation=15, ha="right")
    save_fig(fig, "fig13_classify_confusion.png")
    print(f"\n[分类] {name} 分类报告:")
    print(classification_report(y, y_pred, digits=3))


def plot_importance(model, feature_names: list[str]) -> None:
    imp = pd.Series(model.feature_importances_, index=feature_names).sort_values(ascending=False)
    top = imp.head(15)
    save_table(top.round(5).rename("重要性").to_frame(), "classify_feature_importance.csv", index=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(top.index[::-1], top.values[::-1], color="#55a868")
    ax.set_xlabel("随机森林特征重要性（不纯度下降）")
    ax.set_title("图14 预测性格画像最重要的 15 个特征")
    save_fig(fig, "fig14_classify_importance.png")
    print("[分类] 最重要的 10 个特征:")
    print(top.head(10).round(4).to_string())


def main() -> None:
    X, y, _ = build_dataset()
    models = {
        "逻辑回归": Pipeline([("scaler", StandardScaler()),
                          ("clf", LogisticRegression(max_iter=2000,
                                                     random_state=RANDOM_STATE))]),
        "决策树": DecisionTreeClassifier(max_depth=6, min_samples_leaf=5,
                                     random_state=RANDOM_STATE),
        "随机森林": RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                      random_state=RANDOM_STATE, n_jobs=-1),
    }
    res, preds, _ = evaluate(models, X, y)
    best = res.loc[0, "模型"]
    print(f"[分类] 表现最好的模型: {best}")
    plot_confusion(y, preds[best], best)

    # 用全量数据拟合随机森林，输出特征重要性（解释「什么特征的人属于什么画像」）
    rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                random_state=RANDOM_STATE, n_jobs=-1).fit(X, y)
    plot_importance(rf, X.columns.tolist())

    # 各画像被预测准确率汇总（哪类人最容易识别）
    rep = classification_report(y, preds[best], output_dict=True)
    per_class = pd.DataFrame(rep).T.loc[sorted(y.unique()), ["precision", "recall", "f1-score"]]
    print("\n[分类] 各画像的识别效果:")
    print(per_class.round(3).to_string())
    save_table(per_class.round(4), "classify_per_class.csv", index=True)


if __name__ == "__main__":
    main()

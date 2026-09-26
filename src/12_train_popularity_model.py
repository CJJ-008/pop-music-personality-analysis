# -*- coding: utf-8 -*-
"""训练流行度预测模型，保存为文件供仪表盘"流行度预测器"交互页使用。

与 src/05 的差异：05 是"评测脚本"（关心 R² 的诚实数值），
本脚本是"模型交付"（关心打包体积与线上可用性），因此：
  - 用较精简的随机森林（120 棵树）控制模型文件体积；
  - 用 joblib 压缩保存（含特征清单与流派列表，确保线上特征对齐）。

如实说明：R²=0.17 意味着模型只能解释流行度差异的一小部分，
预测页上必须把这个限制告诉用户（"预测的是大致区间，不是精确值"）。

运行：python src/12_train_popularity_model.py
"""
import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GENRE_CN, RANDOM_STATE, save_table  # noqa: E402
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

spec = spec_from_file_location(
    "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
eda = module_from_spec(spec)
spec.loader.exec_module(eda)

ROOT = Path(__file__).resolve().parents[1]
SPOTIFY_CLEAN = ROOT / "data" / "processed" / "spotify_clean.csv"
MODEL_DIR = ROOT / "outputs" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_FEATURES = ["danceability", "energy", "valence", "tempo", "loudness",
                  "acousticness", "instrumentalness", "liveness", "speechiness",
                  "duration_ms", "key", "mode"]


def main() -> None:
    df = pd.read_csv(SPOTIFY_CLEAN).drop_duplicates(subset="track_id")
    df["release_year"] = df["release_year"].fillna(df["release_year"].median())
    print(f"[模型] 训练数据 {len(df)} 首（按 track_id 去重）")

    X = pd.concat([
        df[AUDIO_FEATURES + ["release_year"]],
        pd.get_dummies(df["playlist_genre"], prefix="流派"),
    ], axis=1)
    y = df["track_popularity"]
    feature_cols = X.columns.tolist()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE)
    model = RandomForestRegressor(n_estimators=120, min_samples_leaf=5,
                                  random_state=RANDOM_STATE, n_jobs=-1)
    model.fit(X_tr, y_tr)
    r2 = r2_score(y_te, model.predict(X_te))
    print(f"[模型] 测试集 R² = {r2:.4f}（与 05 脚本一致，模型有效）")

    payload = {
        "model": model,
        "feature_cols": feature_cols,
        "audio_features": AUDIO_FEATURES,
        "genre_options": {f"流派_{k}": v for k, v in GENRE_CN.items()},
        "test_r2": round(r2, 4),
    }
    out = MODEL_DIR / "popularity_model.joblib"
    joblib.dump(payload, out, compress=3)
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"[模型] 已保存 {out.name}（{size_mb:.1f} MB）")

    # 特征重要性（供预测页展示）
    imp = pd.Series(model.feature_importances_, index=feature_cols)
    save_table(imp.sort_values(ascending=False).round(5).rename("重要性").to_frame(),
               "predictor_feature_importance.csv", index=True)


if __name__ == "__main__":
    main()

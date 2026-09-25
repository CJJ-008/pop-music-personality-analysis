# -*- coding: utf-8 -*-
"""共享配置：项目路径、图表中文字体、存图/存表工具。

所有分析脚本 import 本文件，保证输入输出位置一致。
图表统一用 Microsoft YaHei 显示中文；CSV 结果用 utf-8-sig 编码，
方便直接用 Excel 打开不乱码。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
FIG_DIR = ROOT / "outputs" / "figures"
TAB_DIR = ROOT / "outputs" / "tables"

for _p in (DATA_RAW, DATA_PROC, FIG_DIR, TAB_DIR):
    _p.mkdir(parents=True, exist_ok=True)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]  # Windows 中文字体
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.bbox"] = "tight"

# 两份原始数据文件
SPOTIFY_CSV = DATA_RAW / "spotify_songs.csv"
SURVEY_CSV = DATA_RAW / "responses.csv"
SURVEY_COLS_CSV = DATA_RAW / "columns.csv"

# 清洗后的中间数据
SURVEY_CLEAN_CSV = DATA_PROC / "survey_clean.csv"
SURVEY_CLUSTER_CSV = DATA_PROC / "survey_with_cluster.csv"
SPOTIFY_CLEAN_CSV = DATA_PROC / "spotify_clean.csv"

# Spotify 六大流派中文名
GENRE_CN = {
    "edm": "电子舞曲",
    "latin": "拉丁",
    "pop": "流行",
    "r&b": "R&B",
    "rap": "说唱",
    "rock": "摇滚",
}

# 统一随机种子，保证结果可复现（面试常问点）
RANDOM_STATE = 42


def save_fig(fig, name: str) -> Path:
    """保存图表到 outputs/figures 并打印相对路径。"""
    path = FIG_DIR / name
    fig.savefig(path)
    plt.close(fig)
    print(f"  图已保存: outputs/figures/{name}")
    return path


def save_table(df, name: str, index: bool = False) -> Path:
    """保存结果表到 outputs/tables（utf-8-sig，Excel 可直接打开）。"""
    path = TAB_DIR / name
    df.to_csv(path, index=index, encoding="utf-8-sig")
    print(f"  表已保存: outputs/tables/{name}")
    return path

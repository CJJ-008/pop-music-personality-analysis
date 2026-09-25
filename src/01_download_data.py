# -*- coding: utf-8 -*-
"""数据获取脚本：把两份原始数据下载到 data/raw/。

1. TidyTuesday Spotify 歌曲库 —— GitHub 直链，免登录直接下载；
2. Kaggle Young People Survey —— 先尝试 kagglehub 匿名下载（部分公开数据集
   免账号可用），失败则打印手动下载指引（见 data/README.md）。

重复运行安全：已存在且校验通过的文件会跳过。
"""
import shutil
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA_RAW, SPOTIFY_CSV, SURVEY_CSV, SURVEY_COLS_CSV

SPOTIFY_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/"
    "main/data/2020/2020-01-21/spotify_songs.csv"
)
KAGGLE_DATASET = "miroslavsabo/young-people-survey"


def download_spotify() -> None:
    import pandas as pd

    if SPOTIFY_CSV.exists() and SPOTIFY_CSV.stat().st_size > 1_000_000:
        print(f"[Spotify] 已存在，跳过下载: {SPOTIFY_CSV.name}")
    else:
        print(f"[Spotify] 下载中: {SPOTIFY_URL}")
        try:
            urllib.request.urlretrieve(SPOTIFY_URL, SPOTIFY_CSV)
        except Exception as exc:  # noqa: BLE001 - 打印原因并给出替代命令
            print(f"[Spotify] 下载失败: {exc}")
            print('[Spotify] 可改用命令行下载:')
            print(f'  curl -L -o "{SPOTIFY_CSV}" "{SPOTIFY_URL}"')
            return

    df = pd.read_csv(SPOTIFY_CSV)
    assert df.shape[1] == 23, f"列数异常: {df.shape}"
    print(f"[Spotify] 校验通过: {df.shape[0]} 行 × {df.shape[1]} 列")
    print(f"[Spotify] 流派分布: {df['playlist_genre'].value_counts().to_dict()}")


def download_survey() -> None:
    if SURVEY_CSV.exists() and SURVEY_COLS_CSV.exists():
        print(f"[问卷] 已存在，跳过下载: {SURVEY_CSV.name}, {SURVEY_COLS_CSV.name}")
        return
    try:
        import kagglehub

        print(f"[问卷] 尝试 kagglehub 匿名下载: {KAGGLE_DATASET}")
        path = Path(kagglehub.dataset_download(KAGGLE_DATASET))
        for src_name, dst in (("responses.csv", SURVEY_CSV), ("columns.csv", SURVEY_COLS_CSV)):
            src = next(p for p in path.rglob(src_name))
            shutil.copy(src, dst)
        print(f"[问卷] 匿名下载成功 -> {SURVEY_CSV.parent}")
    except Exception as exc:  # noqa: BLE001
        print(f"[问卷] 匿名下载失败（多数情况需要 Kaggle 账号）: {type(exc).__name__}: {exc}")
        print("[问卷] 请按 data/README.md 的步骤手动下载 responses.csv 与 columns.csv")


if __name__ == "__main__":
    download_spotify()
    print("-" * 50)
    download_survey()

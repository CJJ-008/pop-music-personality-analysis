# -*- coding: utf-8 -*-
"""歌手索引：为「歌手查询（反向推荐）」页构建歌手维度的汇总表。

每行一位歌手（歌曲数 >= 5，保证统计稳定），包含：
  主流派别、歌曲数、平均/最高流行度、平均音频特征（舞蹈性/能量/情绪效价等）、
  发行年份中位数——供查询页展示歌手画像，并与全体歌手的平均水平对比。

运行：python src/11_artist_index.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import GENRE_CN, TAB_DIR, save_table  # noqa: E402
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

spec = spec_from_file_location(
    "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
eda = module_from_spec(spec)
spec.loader.exec_module(eda)

SPOTIFY_CLEAN = Path(__file__).resolve().parents[1] / "data" / "processed" / "spotify_clean.csv"
MIN_SONGS = 5

AUDIO_MEANS = ["danceability", "energy", "valence", "acousticness",
               "instrumentalness", "liveness", "speechiness"]


def main() -> None:
    df = pd.read_csv(SPOTIFY_CLEAN).drop_duplicates(subset="track_id")
    n_songs, n_artists = len(df), df["track_artist"].nunique()
    print(f"[歌手索引] 歌曲 {n_songs} 首，歌手 {n_artists} 位")

    g = (df.groupby("track_artist")
           .agg(歌曲数=("track_id", "size"),
                主流派别=("playlist_genre", lambda s: s.mode().iat[0]),
                平均流行度=("track_popularity", "mean"),
                最高流行度=("track_popularity", "max"),
                发行年份中位数=("release_year", "median"),
                **{f"平均{k}": (k, "mean") for k in AUDIO_MEANS})
           .query("歌曲数 >= @MIN_SONGS")
           .sort_values("平均流行度", ascending=False))
    g["流派中文"] = g["主流派别"].map(GENRE_CN)
    g = g.reset_index().rename(columns={"track_artist": "歌手"})
    print(f"[歌手索引] 歌曲数>={MIN_SONGS} 的歌手 {len(g)} 位")

    # 全体均值（供查询页做"高于/低于平均"对比）
    overall = pd.DataFrame([{
        "歌手": "（全体歌手平均）", "歌曲数": round(n_songs / max(len(g), 1)),
        "平均流行度": round(df["track_popularity"].mean(), 1),
        **{f"平均{k}": round(df[k].mean(), 3) for k in AUDIO_MEANS},
    }])
    ref = pd.concat([overall], ignore_index=True)
    save_table(g.round(3), "artist_index.csv")
    save_table(ref, "artist_overall_reference.csv")

    print(f"[歌手索引] Top5: {g.head(5)['歌手'].tolist()}")
    print(f"[歌手索引] 已保存 artist_index.csv（{len(g)} 行）与 artist_overall_reference.csv")


if __name__ == "__main__":
    main()

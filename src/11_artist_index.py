# -*- coding: utf-8 -*-
"""歌手索引：为「歌手查询（反向推荐）」页构建歌手维度的汇总表。

输出两张表：
  artist_index.csv        每行一位歌手（歌曲数 >= 5，保证统计稳定），包含
                          主流派别、歌曲数、平均/最高流行度、平均音频特征
                          （舞蹈性/能量/情绪效价等）、发行年份中位数——供查询页
                          展示歌手画像，并与全体歌手的平均水平对比；
  artist_top_tracks.csv   每位入索引歌手的代表作（数据集内流行度最高的 5 首），
                          含歌名/流行度/专辑/发行年份——供查询页展示「代表作」。

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
TOP_N = 5  # 每位歌手收录的代表作数量

AUDIO_MEANS = ["danceability", "energy", "valence", "acousticness",
               "instrumentalness", "liveness", "speechiness"]


def build_top_tracks(df: pd.DataFrame, artist_names) -> pd.DataFrame:
    """每位歌手的代表作：数据集内流行度最高的 TOP_N 首。

    并列时按歌名排序，保证结果可复现；歌名/专辑缺失的记录如实标注，不丢行。
    """
    src = (df[df["track_artist"].isin(set(artist_names))]
           .sort_values(["track_artist", "track_popularity", "track_name"],
                        ascending=[True, False, True]))
    top = src.groupby("track_artist", as_index=False).head(TOP_N).copy()
    top["排名"] = top.groupby("track_artist").cumcount() + 1
    top["track_name"] = top["track_name"].fillna("（未标注歌名）")
    top["track_album_name"] = top["track_album_name"].fillna("（未标注专辑）")
    return (top.rename(columns={"track_artist": "歌手", "track_name": "歌曲名",
                                "track_popularity": "流行度",
                                "track_album_name": "专辑", "release_year": "发行年份"})
               [["歌手", "排名", "歌曲名", "流行度", "专辑", "发行年份"]]
               .sort_values(["歌手", "排名"], ignore_index=True))


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

    # 代表作（只覆盖入索引的歌手，保证查询页一定有对应记录）
    top_tracks = build_top_tracks(df, g["歌手"])
    save_table(top_tracks, "artist_top_tracks.csv")

    print(f"[歌手索引] Top5: {g.head(5)['歌手'].tolist()}")
    print(f"[歌手索引] 已保存 artist_index.csv（{len(g)} 行）、artist_overall_reference.csv"
          f" 与 artist_top_tracks.csv（{len(top_tracks)} 行 / {top_tracks['歌手'].nunique()} 位歌手）")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""按描述找歌/找歌手：导出「💬 描述找歌」页所需的 4 张表并做方向自检。

产出（全部入库，云端/exe 直接可用）：
  style_feature_stats.csv  各音频特征的均值与标准差——运行时与预计算同口径的 z 标准化基准
  style_song_matrix.csv    歌级特征表（28356 首 × 17 列，约 3MB）：流派/年份/流行度 +
                           9 个音频特征原值 + key/mode/时长秒——供任意词条组合实时打分
  style_lexicon.csv        中文风格词典（词条 → 检索约束，纯文档用途：词典真源在
                           style_search.py，这里导出一份方便用 Excel 查看增删）
  style_examples.json      界面示例短语

设计要点：
  - 词典与打分逻辑都在根目录 style_search.py（纯逻辑、可单测、随 exe 打包），
    本脚本只负责"把数据准备好 + 验证方向对不对"；
  - 标准化基准单独存表（同 quiz_population_stats.csv 的做法），保证运行时与
    预计算同口径；
  - 自检用真实打分跑一遍典型描述，方向不对就打印"不符合预期!"（照 08 的 sanity 风格）。

运行：python src/13_style_search.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # 根目录：style_search.py
from config import TAB_DIR, save_table  # noqa: E402
import style_search as ss  # noqa: E402

SPOTIFY_CLEAN = Path(__file__).resolve().parents[1] / "data" / "processed" / "spotify_clean.csv"

EXAMPLES = [
    "钢琴伴奏的深夜抒情歌",
    "适合跑步的快节奏电子",
    "失恋后想听的慢歌",
    "小调忧郁的说唱",
    "能蹦迪的夜店舞曲",
    "学习时听的纯音乐",
    "80年代的经典摇滚",
    "安静的咖啡馆音乐",
]


def build_song_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """歌级特征表 + 标准化基准表。z 标准化在运行时用基准表现算，保证同口径。

    歌手/歌名缺失的 4 行如实标注、不丢行（与 11 号脚本的口径一致）。
    """
    feats = ss.Z_FEATURES
    stats = pd.DataFrame({"均值": df[feats].mean().round(4),
                          "标准差": df[feats].std().round(4)})
    stats.index.name = "特征"
    matrix = pd.DataFrame({
        "歌手": df["track_artist"].fillna("（未标注歌手）").values,
        "歌曲名": df["track_name"].fillna("（未标注歌名）").values,
        "流派": df["genre_cn"].values,
        "年份": df["release_year"].astype(int).values,
        "流行度": df["track_popularity"].astype(int).values,
        **{f: df[f].round(3).values for f in feats},
        "key": df["key"].astype(int).values,
        "mode": df["mode"].astype(int).values,
        "时长秒": (df["duration_ms"] / 1000).round().astype(int).values,
    })
    return matrix, stats


def export_lexicon() -> pd.DataFrame:
    """把词典导出成扁平表（一词多约束 = 多行），方便用 Excel 查看。"""
    rows = []
    for term, category, desc, cons in ss.LEXICON:
        if cons and cons[0][0] == "no":
            rows.append({"词条": term, "类别": category, "说明": desc,
                         "约束类型": "不支持", "目标": cons[0][1],
                         "下限": "", "上限": "", "权重": "", "备注": cons[0][2]})
            continue
        for c in cons:
            kind = c[0]
            if kind == "dir":
                rows.append({"词条": term, "类别": category, "说明": desc, "约束类型": "方向",
                             "目标": ss.FEATURE_CN.get(c[1], c[1]), "下限": c[2], "上限": "",
                             "权重": c[3] if len(c) > 3 else 1.0, "备注": ""})
            elif kind == "band":
                rows.append({"词条": term, "类别": category, "说明": desc, "约束类型": "区间",
                             "目标": ss.FEATURE_CN.get(c[1], c[1]),
                             "下限": "" if c[2] is None else c[2],
                             "上限": "" if c[3] is None else c[3],
                             "权重": c[4] if len(c) > 4 else 1.0, "备注": ""})
            elif kind == "genre":
                rows.append({"词条": term, "类别": category, "说明": desc, "约束类型": "流派",
                             "目标": c[1], "下限": "", "上限": "",
                             "权重": c[2] if len(c) > 2 else 1.0, "备注": ""})
            elif kind == "mode":
                rows.append({"词条": term, "类别": category, "说明": desc, "约束类型": "调式",
                             "目标": "大调" if c[1] == 1 else "小调", "下限": c[1], "上限": "",
                             "权重": c[2] if len(c) > 2 else 1.0, "备注": ""})
    return pd.DataFrame(rows)


def sanity_check(matrix: pd.DataFrame, stats: pd.DataFrame) -> None:
    """用真实打分跑几条典型描述，验证检索方向没写反。"""
    checks = [
        ("助眠", "energy", "低于全体"),
        ("蹦迪", "danceability", "高于全体"),
        ("快歌", "tempo", "高于全体"),
        ("纯音乐", "instrumentalness", "高于全体"),
    ]
    print("[描述找歌] 自检：")
    overall = matrix[ss.Z_FEATURES].mean()
    for text, feat, expect in checks:
        q = ss.parse_query(text)
        scored = ss.score_songs(matrix, stats, q, top_n=50)
        top_mean = scored[feat].mean()
        all_mean = overall[feat]
        direction_ok = (top_mean > all_mean) if expect == "高于全体" else (top_mean < all_mean)
        flag = "OK" if direction_ok else "不符合预期!"
        print(f"  「{text}」Top50 {feat} 均值 {top_mean:.3f} vs 全体 {all_mean:.3f} {flag}")

    q = ss.parse_query("说唱")
    scored = ss.score_songs(matrix, stats, q, top_n=50)
    share = (scored["流派"] == "说唱").mean()
    flag = "OK" if share >= 0.8 else "不符合预期!"
    print(f"  「说唱」Top50 中说唱流派占比 {share:.0%} {flag}")

    q = ss.parse_query("老歌")
    scored = ss.score_songs(matrix, stats, q, top_n=50)
    med = scored["年份"].median()
    flag = "OK" if med <= 2000 else "不符合预期!"
    print(f"  「老歌」Top50 年份中位数 {med:.0f} {flag}")


def main() -> None:
    df = pd.read_csv(SPOTIFY_CLEAN).drop_duplicates(subset="track_id")
    print(f"[描述找歌] 歌曲 {len(df)} 首，歌手 {df['track_artist'].nunique()} 位")

    matrix, stats = build_song_matrix(df)
    save_table(matrix, "style_song_matrix.csv")
    save_table(stats, "style_feature_stats.csv", index=True)

    lex = export_lexicon()
    save_table(lex, "style_lexicon.csv")

    (TAB_DIR / "style_examples.json").write_text(
        json.dumps(EXAMPLES, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  表已保存: outputs/tables/style_examples.json")

    sanity_check(matrix, stats)

    print(f"[描述找歌] 词典 {len(ss.LEXICON)} 个词条 / "
          f"{sum(len(cons) for *_, cons in ss.LEXICON)} 条约束；"
          f"示例 {len(EXAMPLES)} 条")
    print("[描述找歌] 已保存 style_song_matrix.csv / style_feature_stats.csv / "
          "style_lexicon.csv / style_examples.json")


if __name__ == "__main__":
    main()

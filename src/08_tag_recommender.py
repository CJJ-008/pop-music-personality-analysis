# -*- coding: utf-8 -*-
"""性格标签推荐器：预计算「标签 × 流派亲和度」矩阵，供仪表盘标签页使用。

设计要点：
- 每个标签锚定真实问卷列（可含反向计分），不是拍脑袋定义；
- 标签的流派亲和度 = 该标签最符合的前 30% 人群的流派均分 − 全体均分
  （沿用全项目统一的「相对偏好」口径）；
- 结果保存到 outputs/tables/ 并入库——云端部署与 exe 都只读结果表，
  因此不依赖原始问卷数据也能给出数据驱动的推荐。

运行：python src/08_tag_recommender.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RANDOM_STATE, TAB_DIR, save_table  # noqa: E402
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

# 复用 02 的列名与流派中文名
spec = spec_from_file_location(
    "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
eda = module_from_spec(spec)
spec.loader.exec_module(eda)

SURVEY_CLEAN = Path(__file__).resolve().parents[1] / "data" / "processed" / "survey_clean.csv"

COHORT_TOP_PCT = 0.30  # 每个标签取最符合的前 30% 作为参考人群

# ---------------------------------------------------------------- 标签库 ----
# (标签名, 分组, [(问卷列, 方向)], 描述)；方向 +1=列高分代表该标签，-1=反向计分
# 二值标签（人口背景）用 (列, "match", 匹配值) 表示
TAG_LIBRARY = [
    # ---- 性格特质（5 对双极，10 个）----
    ("外向爱社交", "性格特质", [("Fun with friends", 1), ("Socializing", 1),
                        ("Number of friends", 1), ("Entertainment spending", 1)],
     "喜欢热闹、朋友多、社交活动丰富"),
    ("安静内向", "性格特质", [("Fun with friends", -1), ("Socializing", -1),
                        ("Number of friends", -1), ("Entertainment spending", -1)],
     "偏好独处与小圈子，社交耗能"),
    ("自律可靠", "性格特质", [("Reliability", 1), ("Keeping promises", 1),
                        ("Punctuality", 1), ("Prioritising workload", 1),
                        ("Thinking ahead", 1)],
     "守时守诺、做事有计划"),
    ("随性散漫", "性格特质", [("Reliability", -1), ("Keeping promises", -1),
                        ("Punctuality", -1), ("Prioritising workload", -1),
                        ("Thinking ahead", -1)],
     "不拘小节、计划性弱"),
    ("情绪稳定", "性格特质", [("Life struggles", -1), ("Mood swings", -1),
                        ("Getting angry", -1), ("Loss of interest", -1),
                        ("Loneliness", -1), ("Hypochondria", -1)],
     "心态平和、抗压能力强"),
    ("感性敏感", "性格特质", [("Life struggles", 1), ("Mood swings", 1),
                        ("Getting angry", 1), ("Loss of interest", 1),
                        ("Loneliness", 1), ("Hypochondria", 1)],
     "情绪起伏大、容易焦虑或低落"),
    ("好奇开放", "性格特质", [("Art exhibitions", 1), ("Theatre", 1), ("Reading", 1),
                        ("Foreign languages", 1), ("Psychology", 1), ("Writing", 1)],
     "兴趣广泛、乐于接触新事物与艺术"),
    ("务实传统", "性格特质", [("Art exhibitions", -1), ("Theatre", -1), ("Reading", -1),
                        ("Foreign languages", -1), ("Psychology", -1), ("Writing", -1)],
     "关注现实事务，对文艺兴趣一般"),
    ("友善体贴", "性格特质", [("Empathy", 1), ("Compassion to animals", 1),
                        ("Giving", 1), ("Charity", 1), ("Borrowed stuff", 1)],
     "有共情心、乐于助人与付出"),
    ("直率独立", "性格特质", [("Empathy", -1), ("Compassion to animals", -1),
                        ("Giving", -1), ("Charity", -1), ("Borrowed stuff", -1)],
     "有主见、以自我目标为先"),
    # ---- 生活方式（8 个）----
    ("运动健将", "生活方式", [("Active sport", 1), ("Adrenaline sports", 1),
                        ("Passive sport", 1)],
     "热爱运动，包括观赛与亲身上阵"),
    ("居家宅", "生活方式", [("Internet", 1), ("PC", 1),
                       ("Countryside, outdoors", -1), ("Active sport", -1)],
     "上网时间长，偏好待在室内"),
    ("购物达人", "生活方式", [("Shopping", 1), ("Shopping centres", 1),
                        ("Branded clothing", 1)],
     "喜欢逛街买东西、认品牌"),
    ("注重外表", "生活方式", [("Spending on looks", 1), ("Appearence and gestures", 1)],
     "在穿着打扮与形象上舍得花钱花心思"),
    ("爱宠物", "生活方式", [("Pets", 1), ("Compassion to animals", 1)],
     "喜欢小动物"),
    ("健康饮食", "生活方式", [("Healthy eating", 1), ("Spending on healthy eating", 1)],
     "注重饮食健康"),
    ("精打细算", "生活方式", [("Finances", 1), ("Economy Management", 1)],
     "关注理财与经济事务"),
    ("追星族", "生活方式", [("Celebrities", 1)],
     "关注名人明星动态"),
    # ---- 兴趣爱好（6 个）----
    ("文艺青年", "兴趣爱好", [("Theatre", 1), ("Art exhibitions", 1), ("Writing", 1)],
     "喜欢戏剧、展览与写作"),
    ("科技极客", "兴趣爱好", [("Science and technology", 1), ("Physics", 1),
                        ("Chemistry", 1), ("PC", 1)],
     "对科学技术与电脑感兴趣"),
    ("书虫", "兴趣爱好", [("Reading", 1)],
     "热爱阅读"),
    ("影视爱好者", "兴趣爱好", [("Movies", 1), ("Documentary", 1)],
     "热爱电影与纪录片"),
    ("历史政治迷", "兴趣爱好", [("History", 1), ("Politics", 1), ("Geography", 1)],
     "关注历史、政治与地理"),
    ("爱好自然", "兴趣爱好", [("Countryside, outdoors", 1), ("Gardening", 1),
                        ("Biology", 1)],
     "喜欢户外、园艺与生物"),
    # ---- 人口背景（2 个，二值）----
    ("城市青年", "人口背景", [("Village - town", "match", "city")],
     "成长于城市"),
    ("小镇青年", "人口背景", [("Village - town", "match", "village")],
     "成长于乡镇"),
]


def tag_score(df: pd.DataFrame, columns: list) -> pd.Series:
    """按标签定义计算每人的标签得分。

    数值列: (列名, +1/-1)，-1 表示反向计分（6-分值）；
    二值列: (列名, "match", 匹配值)，命中为 1 否则 0。
    """
    parts = []
    for spec in columns:
        col, op = spec[0], spec[1]
        if op == "match":
            parts.append((df[col] == spec[2]).astype(float))
        else:
            v = pd.to_numeric(df[col], errors="coerce")
            parts.append(6 - v if op == -1 else v)
    return pd.concat(parts, axis=1).mean(axis=1)


def main() -> None:
    df = pd.read_csv(SURVEY_CLEAN)
    genres = [g for g in eda.MUSIC_GENRES if g in df.columns]
    overall = df[genres].mean()
    print(f"[标签] 数据 {df.shape[0]} 人，流派列 {len(genres)} 个")

    missing = {c for _, cols, _ in [(n, c, d) for n, g, c, d in TAG_LIBRARY]
               for c, *_ in cols} - set(df.columns)
    if missing:
        raise SystemExit(f"[标签] 问卷缺少以下列，请核对: {missing}")

    affinity_rows, def_rows = {}, []
    for name, group, cols, desc in TAG_LIBRARY:
        score = tag_score(df, cols)
        if cols[0][1] == "match":  # 二值标签：参考人群 = 匹配组全体
            cohort = df[score == 1]
            cohort_mode = f"匹配组({cols[0][2]})"
        else:  # 数值标签：参考人群 = 最符合的前 30%
            cutoff = score.quantile(1 - COHORT_TOP_PCT)
            cohort = df[score >= cutoff]
            cohort_mode = f"最符合的前{COHORT_TOP_PCT:.0%}"
        affinity_rows[name] = cohort[genres].mean() - overall
        def_rows.append({"标签": name, "分组": group, "描述": desc,
                         "参考方式": cohort_mode, "参考人数": len(cohort),
                         "来源列": "、".join(c for c, *_ in cols)})

    affinity = pd.DataFrame(affinity_rows).T
    affinity.columns = [eda.GENRE_CN_SURVEY[g] for g in genres]
    affinity.index.name = "标签"

    # ---- sanity 检查：已知关系应成立 ----
    checks = [
        ("好奇开放", "音乐剧", "pos"), ("好奇开放", "歌剧", "pos"),
        ("好奇开放", "嘻哈/说唱", "neg"), ("感性敏感", "摇滚", None),
        ("外向爱社交", "舞曲", None), ("运动健将", "嘻哈/说唱", None),
    ]
    print("\n[标签] Sanity 检查:")
    for tag, genre, expect in checks:
        v = float(affinity.loc[tag, genre])
        flag = "OK" if (expect is None or (expect == "pos") == (v > 0)) else "不符合预期!"
        print(f"  {tag} -> {genre}: {v:+.3f} {flag}")

    print(f"\n[标签] 26 个标签的流派亲和度摘要（每个标签 Top2 流派）:")
    for name in affinity.index:
        top2 = affinity.loc[name].sort_values(ascending=False).head(2)
        print(f"  {name}: " + ", ".join(f"{g} {v:+.2f}" for g, v in top2.items()))

    defs = pd.DataFrame(def_rows)
    save_table(affinity.round(4), "tag_genre_affinity.csv", index=True)
    save_table(defs, "tag_definitions.csv")
    # JSON 版标签定义：给 app.py 做分组 pills 用
    groups = {}
    for name, group, cols, desc in TAG_LIBRARY:
        groups.setdefault(group, []).append(name)
    (TAB_DIR / "tag_groups.json").write_text(
        json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[标签] 已保存 tag_genre_affinity.csv / tag_definitions.csv / tag_groups.json")


if __name__ == "__main__":
    main()

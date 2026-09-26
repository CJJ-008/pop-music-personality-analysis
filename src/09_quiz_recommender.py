# -*- coding: utf-8 -*-
"""性格小测评推荐器：预计算「答题 → 匹配相似人群」所需的基准数据。

设计要点：
- 25 道题全部锚定问卷原始题目（每维度 5 题），与 02 脚本的大五代理指标同源同向，
  保证用户答案可以直接和问卷人群对比；
- 「情绪稳定」维度的题目按困扰方向陈述（分值越高越困扰），计分时反转（6-分值）；
- app.py 运行时拿用户答案与 1010 人逐一算欧氏距离（五维 z 分数空间），
  取最相似的约 10% 人群（101 人），用他们的真实流派打分合成推荐——
  这就是最近邻（KNN）推荐，k 取总量的 10%。

产出（全部入库，云端/exe 直接可用）：
- outputs/tables/quiz_questions.json   25 道题的定义（题干/维度/是否反向）
- outputs/tables/quiz_population_stats.csv  人群五维均值与标准差（用户分数做 z 标准化用）
- outputs/tables/quiz_basis.csv        1010 人的五维 z 分数 + 17 流派打分（KNN 基础表）

运行：python src/09_quiz_recommender.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import RANDOM_STATE, TAB_DIR, save_table  # noqa: E402
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

spec = spec_from_file_location(
    "eda_module", Path(__file__).resolve().parent / "02_clean_eda.py")
eda = module_from_spec(spec)
spec.loader.exec_module(eda)

SURVEY_CLEAN = Path(__file__).resolve().parents[1] / "data" / "processed" / "survey_clean.csv"
K_TOP_PCT = 0.10  # 最近邻人群比例：最像你的前 10%

# ---------------------------------------------------------------- 题库 ----
# (维度, 中文题干, 问卷列, 反向?) —— 反向题按困扰方向陈述，计分时 6-分值
QUIZ_QUESTIONS = [
    # 维度一：外向社交
    ("外向社交", "与朋友一起玩让我感到开心", "Fun with friends", False),
    ("外向社交", "我喜欢主动认识新朋友、参加聚会", "Socializing", False),
    ("外向社交", "我的朋友很多", "Number of friends", False),
    ("外向社交", "我总是精力充沛", "Energy levels", False),
    ("外向社交", "我喜欢唱歌跳舞", "Dancing", False),
    # 维度二：尽责自律
    ("尽责自律", "我是一个可靠的人", "Reliability", False),
    ("尽责自律", "我信守承诺", "Keeping promises", False),
    ("尽责自律", "我做事讲究守时", "Punctuality", False),
    ("尽责自律", "我会先把该做的事做完再去玩", "Prioritising workload", False),
    ("尽责自律", "我工作/学习起来很拼", "Workaholism", False),
    # 维度三：情绪稳定（反向题：分越高越困扰）
    ("情绪稳定", "我的情绪容易大起大落", "Mood swings", True),
    ("情绪稳定", "我容易发脾气", "Getting angry", True),
    ("情绪稳定", "我时常感到孤独", "Loneliness", True),
    ("情绪稳定", "我总担心自己的健康出问题", "Hypochondria", True),
    ("情绪稳定", "生活中的挫折常常让我苦恼", "Life struggles", True),
    # 维度四：开放好奇
    ("开放好奇", "我喜欢读书", "Reading", False),
    ("开放好奇", "我对学习外语有兴趣", "Foreign languages", False),
    ("开放好奇", "我喜欢参观艺术展览", "Art exhibitions", False),
    ("开放好奇", "我对心理学感兴趣", "Psychology", False),
    ("开放好奇", "我对科学技术感兴趣", "Science and technology", False),
    # 维度五：宜人友善
    ("宜人友善", "我能感受到别人的情绪、有同理心", "Empathy", False),
    ("宜人友善", "我喜欢小动物", "Compassion to animals", False),
    ("宜人友善", "我乐于送别人礼物、帮助别人", "Giving", False),
    ("宜人友善", "我愿意参加公益活动", "Charity", False),
    ("宜人友善", "我愿意把东西借给需要的人", "Borrowed stuff", False),
]

TRAITS = ["外向社交", "尽责自律", "情绪稳定", "开放好奇", "宜人友善"]


def main() -> None:
    df = pd.read_csv(SURVEY_CLEAN)
    genres = [g for g in eda.MUSIC_GENRES if g in df.columns]
    genre_cn = [eda.GENRE_CN_SURVEY[g] for g in genres]

    # ---- 1. 人群的五维原始分（与 02 脚本同一套合成规则）----
    trait_raw = {}
    for trait in TRAITS:
        items = [(q_col, q_rev) for q_dim, _, q_col, q_rev in QUIZ_QUESTIONS
                 if q_dim == trait and q_col in df.columns]
        assert len(items) == 5, f"{trait} 题目数异常: {len(items)}"
        parts = [6 - pd.to_numeric(df[c], errors="coerce") if rev
                 else pd.to_numeric(df[c], errors="coerce") for c, rev in items]
        trait_raw[trait] = pd.concat(parts, axis=1).mean(axis=1)
    trait_df = pd.DataFrame(trait_raw)

    # ---- 2. z 标准化基准（人群均值/标准差，供 app 给用户分数做同口径标准化）----
    stats = pd.DataFrame({
        "均值": trait_df.mean().round(4),
        "标准差": trait_df.std().round(4),
    })
    stats.index.name = "维度"

    z = (trait_df - trait_df.mean()) / trait_df.std()
    z.columns = [f"z_{c}" for c in z.columns]

    # ---- 3. KNN 基础表：五维 z 分数 + 17 流派打分 ----
    basis = pd.concat([z, df[genres].set_axis(genre_cn, axis=1)], axis=1)
    basis.index.name = "受访者编号"

    # ---- 4. 保存 ----
    questions = [{"维度": dim, "题干": text, "问卷列": col, "反向计分": rev}
                 for dim, text, col, rev in QUIZ_QUESTIONS]
    (TAB_DIR / "quiz_questions.json").write_text(
        json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    save_table(stats, "quiz_population_stats.csv", index=True)
    save_table(basis.round(4), "quiz_basis.csv", index=True)

    # ---- 5. sanity 检查 ----
    k = max(50, int(round(len(basis) * K_TOP_PCT)))
    print(f"[测评] 题目 {len(questions)} 道，覆盖 {len(TRAITS)} 个维度")
    print(f"[测评] 人群规模 {len(basis)} 人，KNN 取最相似前 {K_TOP_PCT:.0%}（k={k}）")
    print(f"[测评] 人群五维均值: {stats['均值'].round(2).to_dict()}")
    demo_user = {t: stats.loc[t, "均值"] + stats.loc[t, "标准差"] for t in TRAITS}
    uz = {t: (demo_user[t] - stats.loc[t, "均值"]) / stats.loc[t, "标准差"] for t in TRAITS}
    dist = np.sqrt(((z - pd.Series(uz)) ** 2).sum(axis=1))
    top = dist.nsmallest(k).index
    aff = (basis.loc[top, genre_cn].mean() - basis[genre_cn].mean())
    print(f"[测评] 自测样例（全维度偏高的人）最偏爱流派: "
          f"{aff.sort_values(ascending=False).head(3).round(3).to_dict()}")
    print("[测评] 已保存 quiz_questions.json / quiz_population_stats.csv / quiz_basis.csv")


if __name__ == "__main__":
    main()

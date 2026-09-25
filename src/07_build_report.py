# -*- coding: utf-8 -*-
"""生成 Jupyter 分析报告 Notebook（reports/流行音乐数据分析报告.ipynb）。

用 nbformat 程序化生成，保证 JSON 结构合法；报告按分析流程组织，
图表直接引用 outputs/figures/ 下已生成的 PNG，表格读取 outputs/tables/ 的结果 CSV。
"""
import sys
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "流行音乐数据分析报告.ipynb"

nb = nbf.v4.new_notebook()
C: list = []


def md(text: str) -> None:
    C.append(nbf.v4.new_markdown_cell(text.strip()))


def code(src: str) -> None:
    C.append(nbf.v4.new_code_cell(src.strip()))


md("""
# 流行音乐数据分析：什么性格的年轻人喜欢什么样的流行歌手

**大数据专业个人项目** · Python + scikit-learn 全流程分析

---

### 分析链路

```
年轻人问卷(性格+流派偏好) ──► 性格画像聚类 ──► 画像×流派偏好 ──┐
                                                              ├──► 画像 → 流派 → 代表歌手
歌曲库(歌手+流派+音频特征) ──► 流行度回归 ────────────────────┘
```

### 三个可验证的子问题

1. 年轻人按性格可以分成哪几类画像？—— **聚类（K-Means + 层次聚类）**
2. 能否用人口学与兴趣爱好预测一个人属于哪个画像？—— **分类（逻辑回归/决策树/随机森林）**
3. 什么样的歌更容易流行？—— **回归（线性回归 vs 随机森林）**
""")

md("""
## 0. 环境与数据准备

本报告读取 `data/processed/` 下的清洗结果与 `outputs/` 下的图表、结果表。

> 若提示文件不存在，请先在项目根目录按顺序运行：
> `python src/01_download_data.py` → `02_clean_eda.py` → `03_cluster_personality.py`
> → `04_classify_profile.py` → `05_regression_popularity.py` → `06_singer_mapping.py`
""")

code("""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import Image, display, Markdown

# 让 Notebook 无论从哪个目录启动都能找到项目根目录
ROOT = Path.cwd()
while not (ROOT / "src" / "config.py").exists() and ROOT.parent != ROOT:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

FIG = ROOT / "outputs" / "figures"
TAB = ROOT / "outputs" / "tables"


def show_fig(name, width=780):
    \"\"\"展示 outputs/figures 下的图表。\"\"\"
    path = FIG / name
    if path.exists():
        display(Image(filename=str(path), width=width))
    else:
        print(f"[缺失] {path}，请先运行 src 下的分析脚本")


def show_table(name, **kw):
    \"\"\"展示 outputs/tables 下的结果表。\"\"\"
    path = TAB / name
    if path.exists():
        df = pd.read_csv(path, index_col=0 if kw.pop("index", False) else None)
        display(df)
        return df
    print(f"[缺失] {path}")
    return None


pd.set_option("display.unicode.east_asian_width", True)
print("项目根目录:", ROOT)
""")

md("""
## 1. 数据来源与概览

| 数据集 | 内容 | 规模 |
|--------|------|------|
| Young People Survey (Kaggle) | 15~30 岁年轻人：17 个音乐流派 1-5 分偏好、性格与生活态度、人口学 | 1010 人 × 150 列 |
| Spotify Songs (TidyTuesday) | 六大流派歌曲的歌手、流行度、11 个音频特征 | 32833 首（去重后 28356 首），10692 位歌手 |

两份数据通过**流派**这一共同维度桥接。
""")

code("""
survey = pd.read_csv(ROOT / "data/processed/survey_with_cluster.csv")
spotify = pd.read_csv(ROOT / "data/processed/spotify_clean.csv")
spotify_uniq = spotify.drop_duplicates(subset="track_id")

print(f"问卷数据: {survey.shape[0]} 人 × {survey.shape[1]} 列")
print(f"歌曲数据: 原始 {spotify.shape[0]} 行 -> 按 track_id 去重 {spotify_uniq.shape[0]} 首")
print(f"覆盖歌手: {spotify_uniq['track_artist'].nunique()} 位")
print()
print("问卷关键字段示例（人口学 + 性格代理指标）:")
display(survey[["Age", "Gender", "Education", "外向社交", "尽责自律",
                "情绪稳定", "开放好奇", "宜人友善"]].head())
""")

md("""
## 2. 数据清洗与性格维度合成

原始问卷 150 列中有 144 列存在缺失，总缺失率仅 **0.4%**：量表题用中位数填补，
分类题用众数填补。文字选项题（守时、诚实度）序数编码为 1-5 分。

**性格维度合成**：基于大五人格框架，把问卷中语义对应的题目平均成 5 个代理指标，
「情绪稳定」由负向题反向计分得到：

| 维度 | 来源题目（示例） |
|------|------------------|
| 外向社交 | 与朋友玩乐、社交、朋友数量、精力水平、跳舞 |
| 尽责自律 | 可靠性、守信、守时、工作优先、未雨绸缪 |
| 情绪稳定 | 生活挫折、情绪波动、易怒、孤独（**反向计分**） |
| 开放好奇 | 艺术展览、戏剧、阅读、外语、心理学 |
| 宜人友善 | 共情、爱护动物、给予、慈善、诚实度 |

> ⚠️ 这是问卷单题合成的**代理指标**，非标准化大五人格量表（如 NEO-PI-R）。
""")

code("""
display(show_table("survey_proxy_describe.csv", index=True))
display(show_table("survey_genre_means.csv", index=True).head(6))
show_fig("fig01_survey_genre_means.png", 720)
""")

code("""
show_fig("fig02_survey_age_gender.png", 900)
show_fig("fig03_proxy_corr_heatmap.png", 600)
""")

md("""
## 3. 性格聚类：年轻人可分为哪几类画像？

**定 K 规则**：肘部法则看趋势，轮廓系数定候选，取「轮廓系数 ≥ 最优值 90% 的最大 K」。

实测所有 K 的轮廓系数均低于 0.2，说明年轻人的性格**不存在泾渭分明的分群**。
若直接取轮廓系数最大的 K=2，画像过于粗糙，因此在可接受的质量损失内选择更细的 K。
""")

code("""
display(show_table("cluster_k_selection.csv", index=True))
show_fig("fig08_cluster_k_selection.png", 900)
""")

code("""
display(show_table("profile_traits_zscore.csv", index=True))
show_fig("fig09_cluster_pca.png", 720)
show_fig("fig10_profile_traits.png", 760)
""")

code("""
display(show_table("profile_demographics.csv", index=True))
""")

md("""
### 3.1 画像之间的流派偏好差异显著吗？

只看均值差异不够，用 **Kruskal-Wallis 非参数检验**（不假设正态分布，适合 1-5 有序打分）
筛掉不显著的流派，避免把噪声当结论。
""")

code("""
kruskal_df = show_table("profile_genre_kruskal.csv")
n_sig = int((kruskal_df["p值"] < 0.05).sum())
print(f"显著差异流派: {n_sig}/{len(kruskal_df)}")
display(kruskal_df.head(8))
show_fig("fig12_profile_genre_significant.png", 900)
""")

md("""
## 4. 画像 × 流派偏好（核心中间产物）

绝对偏好下所有画像都以流行乐居首，看不出差异；改用**相对全体均值的偏好差异**
才能凸显各画像的特征流派。
""")

code("""
display(show_table("profile_genre_relative.csv", index=True))
show_fig("fig11_profile_genre_heatmap.png", 1000)
display(show_table("profile_favorite_genre.csv", index=True))
""")

md("""
## 5. 画像分类：能否用易得信息预测性格画像？

**方法要点（避免循环论证）**：特征刻意排除 5 个性格维度本身（画像由它们聚类而来）
与 17 个流派打分（音乐口味是待预测结果），只用人口学特征与 44 项兴趣爱好。

业务含义：拿到新用户的年龄、性别、学历、上网时长、兴趣，即可预测其性格画像，
进而推荐该画像偏爱的流派与歌手——一个可落地的推荐前置环节。
""")

code("""
display(show_table("classify_model_comparison.csv"))
show_fig("fig13_classify_confusion.png", 640)
show_fig("fig14_classify_importance.png", 760)
""")

code("""
display(show_table("classify_per_class.csv", index=True))
""")

md("""
## 6. 流行度回归：什么样的歌容易火？

**关键严谨性处理**：原始数据 32833 行中有 4477 行是同一首歌出现在多个歌单，
建模前按 `track_id` 去重，否则同一首歌会同时落进训练集与测试集，造成信息泄漏、R² 虚高。

同时做**消融对比**，量化「流派」特征带来的增益。
""")

code("""
display(show_table("regress_model_comparison.csv"))
show_fig("fig15_regress_pred_scatter.png", 620)
show_fig("fig16_regress_importance.png", 760)
""")

code("""
corr = show_table("regress_corr.csv", index=True)
print("音频特征与流行度的相关系数（全部弱于 |0.15|）:")
display(corr)
""")

md("""
## 7. 核心结论：什么性格的年轻人喜欢什么歌手

把「画像 → 流派偏好」与「流派 → Top 歌手」拼接，得到最终结论表。

**映射说明**：两份数据集不是同一批人，通过「流派」桥接，结论是**画像层面的群体倾向**。
Spotify 数据集只有 6 大流派，问卷中的民谣、乡村、古典、音乐剧、歌剧无对应歌手数据。
""")

code("""
concl = show_table("singer_conclusion_table.csv")
for profile, grp in concl.groupby("性格画像", sort=False):
    display(Markdown(f"### 【{profile}】"))
    for _, r in grp.iterrows():
        note = f"　*{r['解读提示']}*" if isinstance(r.get("解读提示"), str) else ""
        display(Markdown(
            f"- **{r['偏好排名']}：{r['特征流派']}**"
            f"（相对偏好 {r['相对偏好']:+.2f}，绝对倾向 {r['绝对倾向分']}）"
            f"<br>　代表歌手：{r['代表歌手']}{note}"))
""")

code("""
display(show_table("singer_survey_genre_detail.csv"))
show_fig("fig17_profile_spotify_genre.png", 720)
show_fig("fig18_profile_top_artists.png", 1100)
""")

md("""
## 8. 结论与局限

### 主要结论

1. **年轻人可分为 3 个性格画像**：开放好奇·宜人友善型（35.5%）、情绪稳定·外向社交型（34.0%）、
   尽责自律·宜人友善型（30.5%）。其中「情绪稳定·外向社交型」女性仅占 36%，显著偏男性。
2. **性格画像与音乐口味显著相关**：17 个流派中 15 个在画像间差异达 p<0.05，
   差异最大的是音乐剧、歌剧、拉丁、爵士、古典。
3. **性格 → 歌手**：开放好奇型偏拉丁/R&B（Shakira、Billie Eilish、SZA）；
   外向社交型偏说唱/电音（Kendrick Lamar、Timmy Trumpet）；尽责自律型偏好均衡、最接近流行
   （Ed Sheeran、Coldplay）。
4. **画像可预测**：随机森林用易得信息预测画像准确率 **69.2%**，相对基线 35.5% 提升 33.7 个百分点。
5. **歌曲走红主要不由音频特征决定**：回归 R² 仅 0.173，音频特征相关系数全部弱于 |0.15|，
   发行年份反而是最强预测因子（新歌优势）。

### 局限（如实说明）

1. 问卷受访者为斯洛伐克 15~30 岁年轻人，偏好属欧美体系，结论适用于欧美流行音乐语境；
2. 两份数据不是同一批人，通过流派桥接，结论是群体倾向而非个体因果；
3. Spotify 数据仅 6 大流派，问卷中 5 个流派无对应歌手数据（而这恰是画像差异最大的部分）；
4. 性格维度为单题合成的代理指标，非标准化人格量表；
5. 轮廓系数均低于 0.2，画像之间存在重叠，不宜当作硬性分类边界使用。
""")

nb["cells"] = C
nb.metadata = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12"},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, str(OUT))
print(f"已生成: {OUT.relative_to(ROOT)}（{len(C)} 个单元格）")

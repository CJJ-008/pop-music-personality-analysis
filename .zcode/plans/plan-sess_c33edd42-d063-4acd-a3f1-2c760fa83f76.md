# 流行音乐数据分析项目 — 实施计划

## 项目定位
「什么性格的年轻人喜欢什么流行歌手」——大数据专业简历项目。分析链路：
**年轻人问卷(性格+流派打分) → 聚类出性格画像 → 画像×流派偏好 → 流派↔代表歌手映射 → 歌曲流行度回归**

## 一、数据（已由你拍板）
1. **性格侧**：Kaggle [Young People Survey](https://www.kaggle.com/datasets/miroslavsabo/young-people-survey)（1010 人 × 150 列，15~30 岁，16 个音乐流派 1-5 分 + 性格/生活习惯题）
   - 需要你**注册一个免费 Kaggle 账号**后浏览器手动下载 `responses.csv` + `columns.csv`，放到 `data/raw/`（我会在实施时给出逐步指引；此文件无法免登录直连下载）
2. **歌手侧**：TidyTuesday [Spotify Songs](https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2020/2020-01-21/spotify_songs.csv)（32,833 首 × 23 列，六大流派、歌手、流行度、11 个音频特征）
   - GitHub 直链，我直接用 curl 帮你下载到 `data/raw/`
3. 华语歌手模块：本期不做（你已确认）

## 二、项目结构（git 仓库根 = E:\流行音乐数据分析）
```
├── zcode.md            # 你的需求与决策记录（第一件交付物）
├── README.md           # 简历用项目说明+成果图
├── .gitignore          # 原始数据、环境文件、临时文件不入库
├── data/raw|processed/ # 原始与清洗后数据（不入 git，附下载脚本）
├── src/                # 01下载数据 → 02清洗EDA → 03性格聚类 → 04画像分类 → 05流行度回归 → 06画像×歌手映射
├── notebooks/          # Jupyter 全流程分析报告（面试可展示）
└── outputs/figures|tables/  # 图表（PNG 小图入 git，简历展示用）
```

## 三、分析方案（经典三件套，sklearn 全覆盖）
1. **EDA+清洗**：缺失值、1-5 分量表标准化、性格题目合成性格维度得分（外向性/尽责性/情绪敏感等代理指标，方法会写进报告）
2. **聚类**：K-Means 为主（肘部法则+轮廓系数定 K，PCA 二维可视化），层次聚类作对比 → 输出 4~6 类年轻人画像并命名（如外向社交型/宅家自律型）
3. **分类**：逻辑回归 vs 决策树 vs 随机森林，预测受访者属于哪个画像簇；交叉验证+混淆矩阵+特征重要性 → 回答"什么特征的人属于什么画像"
4. **回归**：线性回归（基线）vs 随机森林回归，用音频特征预测歌曲流行度 track_popularity，R²/RMSE + 特征重要性 → 回答"什么样的歌容易火"
5. **画像×歌手映射**：每个流派取流行度 Top 歌手，结合画像×流派偏好矩阵，产出核心结论表「外向型年轻人 → Pop/Rap → 代表歌手…」
6. **可视化**：聚类散点图、画像×流派热力图、Top 歌手柱状图、回归预测散点图（matplotlib/seaborn）

技术栈：pandas/numpy/matplotlib/seaborn/scikit-learn/scipy，全部来自你已装的 Anaconda；PyTorch、Java 本期不用（你已确认经典三件套）。

## 四、Git 管理（本地+GitHub，你已拍板）
- `git init` + `.gitignore`，按阶段提交：①初始化与 zcode.md ②数据脚本 ③清洗EDA ④聚类 ⑤分类 ⑥回归 ⑦歌手映射与报告 ⑧README 定稿
- GitHub 远程：需要你有 GitHub 账号（没有我给你注册指引）；本地提交全部做好后，我协助你把远程仓库配上并推送，实现异地备份

## 五、协作原则（写入 zcode.md）
每个阶段性方案先向你解释、由你拍板再动手；本次已记录 4 项决策（数据集组合/华语模块/算法范围/Git 方案）。

## 执行顺序
zcode.md + git 初始化 → 指引你下载 Kaggle 文件（同时我下载 Spotify 数据）→ 清洗 EDA → 三件套建模 → 歌手映射与可视化 → Notebook 报告 + README → 提交与远程仓库配置。
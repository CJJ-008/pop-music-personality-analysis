# zcode.md — 项目需求与决策记录

> 本文件是「流行音乐数据分析」项目的需求与决策档案，由学生本人提出要求、ZCode 协助整理与维护。
> 项目定位：**可写入简历的大数据分析项目**。任何新的关键决定，先更新本文件再实施。

## 一、项目背景与目标

- 我的身份：大数据专业学生，需要一个能写进简历、经得起面试追问的完整数据分析项目。
- 项目主题：**分析什么性格的年轻人喜欢什么样的流行歌手**。
- 产出目标：完整可复现的分析流水线（Python 脚本）+ 可视化图表 + 分析报告（Jupyter Notebook）+ README（简历可直接引用的项目描述）。

## 二、原始需求清单（逐条记录）

| 编号 | 需求内容 | 说明 |
|------|----------|------|
| R1 | 完成一个可写入简历的流行音乐数据分析项目 | 成果要能支撑简历上的项目经历描述 |
| R2 | 分析主题：什么性格的年轻人喜欢什么样的流行歌手 | 核心业务问题 |
| R3 | 从全网寻找包含歌手、乐曲等信息的数据集，候选方案交由我做决定 | 已完成调研，见决策记录 D1 |
| R4 | 技术栈：Python、Java；PyCharm 中部署了 Anaconda 环境（含 PyTorch、numpy 等） | 见第三章 |
| R5 | 必须使用数据分析常用算法：聚类、分类、回归 | 见决策记录 D3 |
| R6 | 项目加入 git 管理、存档，避免代码丢失 | 见决策记录 D4、第八章 |
| R7 | 每个要采用的方案都向我解释一遍，由我来做决定 | 协作原则，见第十章 |
| R8 | 将以上要求详细记录在 zcode.md | 即本文件 |

## 三、技术栈（已确认）

- 主力语言：**Python 3.12**（本机 D:\python，已验证 pandas / numpy / scikit-learn / matplotlib / seaborn / scipy 全部可用）
- 环境管理：Anaconda（E:\Anaconda）已安装，PyCharm 中已部署环境
- 版本管理：git（本地仓库 + GitHub 远程备份）
- 本期不使用：Java、PyTorch（见决策记录 D3，采用经典三件套方案）

## 四、关键决策记录

| 编号 | 决策点 | 备选方案 | 最终决定 | 日期 | 状态 |
|------|--------|----------|----------|------|------|
| D1 | 数据集组合 | ①年轻人问卷 + 3.2万歌曲库（推荐）②再加 2023 热歌 ③问卷 + 2023 热歌 ④心理健康问卷 + 歌曲库 | **① 年轻人问卷 + 3.2万歌曲库** | 2026-09-25 | 已定 |
| D2 | 华语歌手模块 | ①暂不加（推荐）②加网易云歌单爬虫模块 | **暂不加**（Kaggle/GitHub 无现成华语歌手 CSV 数据集，爬虫风险大） | 2026-09-25 | 已定 |
| D3 | 算法范围 | ①经典三件套：聚类 + 分类 + 回归（推荐）②再加 PyTorch 神经网络加分项 | **经典三件套** | 2026-09-25 | 已定 |
| D4 | Git 存档方案 | ①本地 + GitHub 远程（推荐）②本地 + Gitee ③仅本地 | **本地 + GitHub 远程** | 2026-09-25 | 已定 |
| D5 | Kaggle 问卷数据获取方式 | ①kagglehub 匿名自动下载 ②注册 Kaggle 后浏览器手动下载 | **① 匿名下载成功，无需注册 Kaggle** | 2026-09-25 | 已解决 |

## 五、数据集档案

### 5.1 性格侧：Kaggle Young People Survey（待入库）

- 地址：<https://www.kaggle.com/datasets/miroslavsabo/young-people-survey>
- 规模：1010 名受访者（斯洛伐克，15~30 岁）× 150 列
- 关键字段：音乐流派偏好打分（1-5 分，Pop / Rock / Rap / Techno 等 16+ 项）、性格与生活态度题（可靠性、守承诺、自律、生活压力感等）、消费习惯、人口学特征（年龄/性别/学历/城乡）
- 文件：`responses.csv`（数据）+ `columns.csv`（列含义说明）→ 放入 `data/raw/`
- 下载方式：见 `data/README.md`

### 5.2 歌手侧：TidyTuesday Spotify Songs（可免登录直链下载）

- 地址：<https://github.com/rfordatascience/tidytuesday/tree/main/data/2020/2020-01-21>
- 直链：<https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/data/2020/2020-01-21/spotify_songs.csv>
- 规模：32,833 首 × 23 列；六大流派：edm（电子舞曲）/ latin（拉丁）/ pop（流行）/ r&b / rap（说唱）/ rock（摇滚）
- 关键字段：`track_artist`（歌手）、`track_popularity`（流行度 0-100）、`playlist_genre`（流派）、11 个音频特征（danceability 舞蹈性、energy 能量、valence 情绪效价、acousticness 原声度等）
- 文件：`spotify_songs.csv` → 放入 `data/raw/`，由 `src/01_download_data.py` 自动下载

### 5.3 数据限制（面试可能被问到，如实记录）

- 问卷来自斯洛伐克 15~30 岁年轻人，流派偏好为欧美体系，结论适用于欧美流行音乐语境；
- Spotify 数据为 2020 年 1 月抓取的六大流派歌单歌曲，不代表全平台全量音乐；
- 两份数据通过「流派」桥接，不是同一批人的直接听歌记录，因此歌手结论是画像层面的映射而非因果。

## 六、分析方案（已批准）

分析链路：
**年轻人问卷(性格+流派打分) → 聚类出性格画像 → 画像×流派偏好 → 流派↔代表歌手映射 → 歌曲流行度回归**

1. **清洗与 EDA**（`src/02_clean_eda.py`）：缺失值处理、1-5 分量表、描述统计、分布图
2. **聚类**（`src/03_cluster_personality.py`）：由性格/生活题目合成性格维度得分 → K-Means（肘部法则 + 轮廓系数选 K）为主，层次聚类对比，PCA 二维可视化 → 输出 4~6 类年轻人性格画像并命名
3. **分类**（`src/04_classify_profile.py`）：逻辑回归 vs 决策树 vs 随机森林，预测受访者属于哪个画像簇；5 折交叉验证 + 混淆矩阵 + 特征重要性
4. **回归**（`src/05_regression_popularity.py`）：线性回归（基线）vs 随机森林回归，用音频特征预测歌曲流行度 `track_popularity`；R² / RMSE + 特征重要性
5. **画像×歌手映射**（`src/06_singer_mapping.py`）：每个流派取流行度 Top 歌手，结合画像×流派偏好矩阵，产出核心结论表「某画像年轻人 → 偏爱流派 → 代表歌手」
6. **可视化**：聚类散点图、画像×流派热力图、Top 歌手柱状图、回归预测散点图（matplotlib/seaborn，图入库 `outputs/figures/`）

## 七、项目结构

```
E:\流行音乐数据分析\
├── zcode.md              # 本文件：需求与决策记录（入 git）
├── README.md             # 简历用项目说明（入 git）
├── .gitignore            # 数据、缓存不入库（入 git）
├── data/
│   ├── README.md         # 数据下载指引（入 git）
│   ├── raw/              # 原始数据（不入 git，见 data/README.md）
│   └── processed/        # 清洗后数据（不入 git，脚本可重新生成）
├── src/                  # 分析脚本（按编号即执行顺序）
│   ├── config.py         # 共享配置：路径、中文字体、存图存表工具
│   ├── 01_download_data.py
│   ├── 02_clean_eda.py
│   ├── 03_cluster_personality.py
│   ├── 04_classify_profile.py
│   ├── 05_regression_popularity.py
│   └── 06_singer_mapping.py
├── notebooks/            # Jupyter 探索草稿
├── reports/              # 最终分析报告 Notebook（入 git）
└── outputs/
    ├── figures/          # 图表 PNG（入 git，简历展示用）
    └── tables/           # 结果表 CSV（入 git，结论支撑）
```

## 八、Git 规范

- 提交信息格式：`类型: 中文描述`（类型：chore / data / analysis / docs）
- 数据文件（data/raw、data/processed）不入库；图表 PNG 与结果表 CSV 入库
- 阶段提交清单：
  - [ ] ① chore: 项目初始化（目录结构、zcode.md、.gitignore）
  - [ ] ② data: 数据下载脚本与数据入库验证
  - [ ] ③ analysis: 清洗与 EDA
  - [ ] ④ analysis: 性格聚类
  - [ ] ⑤ analysis: 画像分类
  - [ ] ⑥ analysis: 流行度回归
  - [ ] ⑦ analysis: 画像×歌手映射
  - [ ] ⑧ docs: 分析报告与 README 定稿
- 远程仓库：GitHub（待注册账号后配置 `git remote` 并推送，见 D4）

## 九、进度跟踪

- [x] 数据集全网调研与选定（D1）
- [x] 项目结构 + zcode.md + .gitignore
- [ ] git 初始化与首次提交
- [ ] Spotify 歌曲数据下载入库
- [ ] Kaggle 问卷数据入库（等待：匿名下载尝试 / 我注册 Kaggle 后手动下载）
- [ ] 清洗与 EDA
- [ ] 聚类（性格画像）
- [ ] 分类（画像预测）
- [ ] 回归（流行度预测）
- [ ] 画像×歌手映射
- [ ] Jupyter 分析报告
- [ ] README 定稿
- [ ] GitHub 远程仓库配置与推送

## 十、协作原则（R7 的落实方式）

1. 每个要采用的方案（数据集选择、算法选型、Git 方案等）先向学生本人解释利弊，由本人拍板后再动手；
2. 纯技术细节（如缺失值填补方式、随机种子、图配色）由 ZCode 按数据分析惯例决定，但会记录在代码注释与本文件中；
3. 任何偏离本文件的新决定，先更新第四章决策表再实施。

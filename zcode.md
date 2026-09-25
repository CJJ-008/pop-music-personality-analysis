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
| D6 | 聚类数 K 的选取规则 | ①直接取轮廓系数最大的 K=2 ②取「轮廓系数 ≥ 最优值 90% 的最大 K」 | **②**（K=2 画像过粗，业务价值低；实测所有 K 的轮廓系数均 <0.2，在可接受损失内换取更细划分，并在报告中如实披露） | 2026-09-25 | 已定 |
| D7 | 画像偏好排序依据 | ①绝对偏好分 ②相对全体均值的偏好差异 | **②相对偏好**（绝对分下三个画像都以流行乐居首，看不出差异；相对偏好才能凸显特征流派） | 2026-09-25 | 已定 |
| D8 | 分类任务特征范围 | ①含性格维度与流派打分 ②仅人口学+兴趣爱好 | **②**（画像由性格维度聚类而来，用它们预测等于答案泄漏；流派打分是待预测结果，不能当输入，否则构成循环论证） | 2026-09-25 | 已定 |
| D9 | 回归建模是否去重 | ①直接用全部 32833 行 ②按 track_id 去重 | **②去重后 28356 首**（原始数据 4477 行是同一首歌出现在多个歌单，不去重会导致同一首歌跨训练/测试集，R² 虚高） | 2026-09-25 | 已定 |
| D10 | GitHub 远程推送方式 | ①HTTPS（凭证管理器弹浏览器登录）②SSH 22 端口 ③SSH 443 端口 | **①HTTPS**（实测：SSH 22 端口被网络拒绝；本机 SSH 密钥是 Gitee 的，未在 GitHub 注册；HTTPS 走凭证管理器正常） | 2026-09-25 | 已完成 |
| D11 | 仓库可见性 | ①公开 ②私有 | **①公开**（简历项目需给招聘方查看；账号 CJJ-008 原有 2 个仓库均为公开，保持风格一致。如需改为私有：GitHub 仓库 Settings → 最下方 Danger Zone → Change visibility） | 2026-09-25 | 已定 |
| D12 | 可视化界面方案 | ①仅用现有 Jupyter 报告 ②仅开发 Streamlit 仪表盘 ③两者都要 | **③两者都要**（Jupyter 报告保留 + 新增 Streamlit 歌手推荐器网页） | 2026-09-25 | 已定 |
| D13 | 仪表盘板块范围 | 数据总览 / 性格画像 / 歌手推荐器 / 模型结果（可多选） | **只做「歌手推荐器」核心板块**（选画像 → 看流派 → 看代表歌手） | 2026-09-25 | 已定 |
| D14 | 仪表盘是否部署公网 | ①仅本地 localhost ②部署 Streamlit Community Cloud（免费） | **②部署**（得到公开网址可写进简历做"在线演示"；需本人网页授权 GitHub 登录） | 2026-09-25 | 进行中 |
| D15 | 仪表盘认证方式 | ①自写密码登录（bcrypt+secrets）②Streamlit 原生 OAuth（Google/GitHub）③多用户库 streamlit-authenticator | **③多用户库**（自带登录/注册界面、bcrypt 哈希、图形验证码、Cookie 记住登录） | 2026-09-25 | 已定 |
| D16 | 访问控制策略 | ①必须登录 ②保留游客入口 ③登录页给演示账号 | **①必须登录**（已如实记录副作用：配合"开放注册"后实际是"任何人注册即可进"，防护意义有限，主要价值是演示完整认证流程） | 2026-09-25 | 已定 |
| D17 | 是否支持注册 | ①仅固定账号 ②支持自助注册 | **②支持注册**（带图形验证码；注册用户持久化到 data/users.json） | 2026-09-25 | 已定 |
| D18 | 仪表盘分发方式 | ①仅云部署 ②云部署+PyInstaller 打包 exe ③仅 exe ④换桌面框架重写 | 先定①，后**应用户要求补做②的 exe 部分**（见 D19） | 2026-09-25 | 已调整 |
| D19 | exe 打包 | PyInstaller 6.21 单文件模式 / onedir / 桌面框架重写 | **PyInstaller 单文件**：`性格歌手推荐器.exe`（274MB，含登录/注册与全部数据），构建产物不入库（超 GitHub 单文件 100MB 限制）。已解决三个打包坑：magic_funcs 动态导入、依赖库数据文件、冻结模式路径分流；浏览器端到端验证通过 | 2026-09-25 | 已完成 |

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
├── app.py                # Streamlit 歌手推荐器仪表盘（入 git）
├── requirements.txt      # 锁定版本的依赖清单（入 git，云端部署必需）
├── .python-version       # 指定 Python 3.12（入 git，云端部署用）
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
│   ├── 06_singer_mapping.py
│   └── 07_build_report.py  # 程序化生成 Jupyter 分析报告（保证可复现）
├── scripts/
│   └── setup_github.sh     # GitHub 远程仓库配置脚本
├── notebooks/            # Jupyter 探索草稿
├── reports/              # 最终分析报告 Notebook（入 git）
└── outputs/
    ├── figures/          # 18 张图表 PNG（入 git，简历展示用）
    └── tables/           # 22 张结果表 CSV（入 git，结论支撑 + 仪表盘数据源）
```

## 八、Git 规范

- 提交信息格式：`类型: 中文描述`（类型：chore / data / analysis / docs）
- 数据文件（data/raw、data/processed）不入库；图表 PNG 与结果表 CSV 入库
- 阶段提交清单（全部完成）：
  - [x] ① chore: 项目初始化（目录结构、zcode.md、.gitignore）
  - [x] ② data: 数据下载脚本与数据入库验证
  - [x] ③ analysis: 清洗与 EDA
  - [x] ④ analysis: 性格聚类
  - [x] ⑤ analysis: 画像分类
  - [x] ⑥ analysis: 流行度回归
  - [x] ⑦ analysis: 画像×歌手映射
  - [x] ⑧ docs: 分析报告与 README 定稿
  - [x] ⑨ chore: 配置 GitHub 远程仓库并推送
- 远程仓库：GitHub（待注册账号后配置 `git remote` 并推送，见 D4）

## 九、进度跟踪（全部完成）

- [x] 数据集全网调研与选定（D1）
- [x] 项目结构 + zcode.md + .gitignore
- [x] git 初始化与首次提交
- [x] Spotify 歌曲数据下载入库（32833 行 × 23 列）
- [x] Kaggle 问卷数据入库（kagglehub 匿名下载成功，1010 行 × 150 列，无需注册账号）
- [x] 清洗与 EDA（生成图 1~7）
- [x] 聚类（性格画像 K=3，含层次聚类对比与 Kruskal-Wallis 检验）
- [x] 分类（画像预测，随机森林 69.2% vs 基线 35.5%）
- [x] 回归（流行度预测，随机森林 R²=0.173）
- [x] 画像×歌手映射（核心结论表 + 图 17~18）
- [x] Jupyter 分析报告（已执行验证，0 报错）
- [x] README 定稿
- [x] 可复现性验证：克隆到临时目录后从零运行全流程，关键结果表与原仓库逐字节一致
- [x] GitHub 远程仓库配置与推送完成
      → 仓库地址：<https://github.com/CJJ-008/pop-music-personality-analysis>
      → 远程 main 与本地 HEAD 完全同步（56 个文件），数据文件按 .gitignore 正确排除
- [x] 修复 03 脚本 DataFrame 碎片化警告（pd.concat 替代逐列赋值，重跑结果不变）
- [x] Streamlit 歌手推荐器仪表盘（app.py，AppTest 三画像冒烟测试 0 异常 + 服务器健康检查 200）
- [x] requirements.txt（锁定版本）与 .python-version 部署配置
- [x] 仪表盘登录/注册功能（D15~D17）：auth.py + streamlit-authenticator 0.4.2
      → 凭据存 st.secrets（只提交 .example 模板），密码 bcrypt 哈希，图形验证码
      → 注册用户持久化到 data/users.json（库自身不落盘，必须自己实现）
      → 已测：门禁零泄漏、正确/错误密码、注册落盘无明文、全新会话下两类账号均可登录
- [x] exe 打包完成（D19）：PyInstaller 单文件 274MB
      → launcher.py + streamlit_app.spec；解决 magic_funcs 动态导入、依赖库数据文件、
        冻结模式路径（资源在 _MEIPASS / 可写文件在 exe 旁）三大问题
      → 浏览器端到端验证：登录页渲染 → admin 登录 → 仪表盘/雷达图/歌手推荐全部正常 →
        Cookie 免登录直达；密码在发行包中只存 bcrypt 哈希
- [ ] Streamlit Community Cloud 部署（D14：等我在网页上用 GitHub 账号授权部署，拿到网址后回填 README）

## 九之五、认证功能的技术细节与已知限制

### 实现要点
- **凭据来源**：`st.secrets`（本地 `.streamlit/secrets.toml` / 线上 Cloud 面板），
  仓库只提交 `.streamlit/secrets.toml.example` 模板；真实 secrets 与 `data/users.json` 均已 gitignore
- **密码存储**：bcrypt 哈希（`$2b$` 开头），任何环节不保存明文；已验证提交内容无明文泄漏
- **注册持久化**：库的 `register_user` 只改内存字典、不写文件，而 Streamlit 每次交互
  都会重建认证对象 → 自己实现 `data/users.json` 读写，与 secrets 预置账号合并（同名以预置账号优先）
- **安全测试**：未登录时仪表盘内容零泄漏；错误密码/不存在用户均被拦截

### 踩到的两个坑
1. `st.secrets` 是**只读对象**，而库内部要回写哈希后的密码 →
   `TypeError: Secrets does not support item assignment`。
   浅拷贝无效（嵌套层仍只读），须递归深拷贝为普通 dict。
2. `Authenticate` 视图对象**不暴露** `credentials`，它在
   `authentication_controller.authentication_model.credentials`；已做多路径兜底。

### 已知限制（如实记录，不可对外夸大）
1. **线上注册账号不持久**：Streamlit Community Cloud 文件系统是临时的，应用重启/
   重新部署后 `data/users.json` 被重置，注册账号丢失（secrets 预置账号不受影响）。
   真正长期持久化需接外部数据库（Supabase/PostgreSQL），属后续扩展。
2. **防护意义有限**：D16 选"必须登录"同时 D17 选"支持注册"，实际效果是
   "任何人注册一下就能进"，安全性提升有限，价值在于演示完整认证流程。

## 九之四、仪表盘说明（app.py）

- **定位**：交互式网页版「性格 × 流行歌手推荐器」，是 Jupyter 图文报告之外的另一种查看方式
- **数据源**：只读 `outputs/tables/` 里已入库的结果表，不依赖原始数据——克隆仓库或云端部署
  后无需重新跑分析，冷启动即可用
- **内容**：侧边栏切换 3 个性格画像 → 画像人口学卡片 + 五维性格雷达图（plotly）→
  第 1/2 特征流派与相对偏好 → 该流派 Top 歌手条形图与推荐名单
- **本地运行**：`pip install -r requirements.txt` 后执行 `streamlit run app.py`
- **已验证**：Streamlit AppTest 三画像切换 0 异常；真实服务器 health check 返回 ok

## 九之三、项目交付清单

| 交付物 | 位置 | 说明 |
|--------|------|------|
| 需求与决策档案 | `zcode.md` | 17 项决策记录、完整结果、踩坑记录 |
| 简历用项目说明 | `README.md` | 含核心结论表、技术亮点、局限说明 |
| 分析报告 | `reports/流行音乐数据分析报告.ipynb` | 26 单元格，已执行验证 0 报错 |
| 交互式仪表盘 | `app.py` + `auth.py` | Streamlit 歌手推荐器 + 登录注册认证 |
| 分析脚本 | `src/01`~`07` | 数据获取 → 清洗 → 聚类 → 分类 → 回归 → 映射 → 报告生成 |
| 图表 | `outputs/figures/` | 18 张，全部中文渲染，已通过视觉检查 |
| 结果表 | `outputs/tables/` | 22 张 CSV，Excel 可直接打开，也是仪表盘数据源 |
| 部署配置 | `requirements.txt` + `.python-version` + `.streamlit/secrets.toml.example` | 锁定版本与凭据模板 |
| 远程备份 | GitHub `CJJ-008/pop-music-personality-analysis` | 公开仓库，异地备份已完成 |

## 九之二、实际分析结果（供简历与答辩引用）

### 数据规模
- 问卷：1010 名 15~30 岁年轻人 × 150 列，总缺失率 0.4%（144 列有缺失）
- 歌曲：32833 行 → 按 track_id 去重后 **28356 首**，覆盖 **10692 位歌手**，六大流派

### 聚类结果（K-Means，K=3，轮廓系数 0.170）

| 性格画像 | 人数 | 占比 | 女性占比 | 特征流派 | 代表歌手 |
|----------|------|------|----------|----------|----------|
| 开放好奇·宜人友善型 | 359 | 35.5% | 73% | 拉丁、R&B（问卷侧最爱音乐剧/爵士/古典/歌剧） | Shakira、Maluma、Billie Eilish、SZA |
| 情绪稳定·外向社交型 | 343 | 34.0% | **36%** | 说唱、电子舞曲 | Kendrick Lamar、Young Thug、Timmy Trumpet |
| 尽责自律·宜人友善型 | 308 | 30.5% | 69% | 流行（各流派偏好均衡，无突出偏好） | Ed Sheeran、Coldplay、Camila Cabello |

- 层次聚类（Ward）与 K-Means 的 ARI = 0.364
- Kruskal-Wallis 检验：**15/17** 个流派的画像间差异显著（p<0.05），差异最大为音乐剧(H=82.2)、歌剧(77.6)、拉丁(65.2)

### 分类结果（预测性格画像）

| 模型 | 准确率 | 宏平均 F1 |
|------|--------|-----------|
| 基线（全猜最多类） | 35.5% | — |
| 逻辑回归 | 67.6% | 0.674 |
| 决策树 | 57.3% | 0.571 |
| **随机森林** | **69.2%** | **0.686** |

最重要特征：极限运动、艺术展览、戏剧、跳舞、身高体重

### 回归结果（预测歌曲流行度）

| 模型 | 特征集 | R² | RMSE |
|------|--------|-----|------|
| 线性回归 | 仅音频+年份 | 0.057 | 23.02 |
| 随机森林 | 仅音频+年份 | 0.135 | 22.04 |
| 线性回归 | 音频+年份+流派 | 0.087 | 22.64 |
| **随机森林** | **音频+年份+流派** | **0.173** | **21.56** |

- 最强预测因子是**发行年份**（重要性 0.129），反映流行度指标的「新歌优势」
- 音频特征与流行度相关系数全部弱于 |0.15| → 歌曲走红主要不由音频特征决定

### 已解决的技术问题（面试可讲）

1. **pandas 3.0 类型陷阱**：新字符串类型为 `str` 而非 `object`，导致「守时」等文字选项题被误当作 1-5 打分题参与均值合成（报错 `Cannot perform reduction 'median' with string dtype`）。改为先序数编码为 1-5 分，并加数值类型守卫。
2. **matplotlib 数学模式陷阱**：歌手名 `$uicideBoy$` 中的 `$...$` 被当作 LaTeX 公式解析，符号被吞掉、文字变斜体。通过在标签中转义 `$` 修复。
3. **E 盘文件系统不记录所有权**导致 git 报 `dubious ownership`，通过 `git config --global --add safe.directory` 解决。
4. **信息泄漏**：回归前按 track_id 去重，避免同一首歌跨训练/测试集。
5. **循环论证**：分类特征排除性格维度与流派打分。

## 十、协作原则（R7 的落实方式）

1. 每个要采用的方案（数据集选择、算法选型、Git 方案等）先向学生本人解释利弊，由本人拍板后再动手；
2. 纯技术细节（如缺失值填补方式、随机种子、图配色）由 ZCode 按数据分析惯例决定，但会记录在代码注释与本文件中；
3. 任何偏离本文件的新决定，先更新第四章决策表再实施。

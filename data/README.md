# 数据文件说明（本目录内容不入 git）

两份数据集放这里后，分析脚本即可运行。**原始数据不入 git**（体积大、可重新获取），
下载脚本见 `src/01_download_data.py`，运行后可自动校验文件完整性。

## 需要的文件

| 文件 | 来源 | 大小 | 用途 | 获取方式 |
|------|------|------|------|----------|
| `spotify_songs.csv` | TidyTuesday (GitHub) | ~7 MB | 歌手/流派/流行度/音频特征 | **免登录**，`python src/01_download_data.py` 自动下载 |
| `responses.csv` | Kaggle Young People Survey | ~86 KB | 年轻人性格与音乐偏好问卷 | 需 Kaggle 账号（免费），见下方步骤 |
| `columns.csv` | 同上 | ~8 KB | 问卷每列的含义说明 | 同上 |

## Kaggle 问卷数据手动下载步骤（约 5 分钟）

1. 注册/登录 <https://www.kaggle.com>（仅需邮箱，免费）
2. 打开数据集页面：<https://www.kaggle.com/datasets/miroslavsabo/young-people-survey>
3. 点击页面右上角红色 **Download** 按钮（约 100 KB 的 zip 包）
4. 解压后把 `responses.csv` 和 `columns.csv` 两个文件放进本项目 `data/raw/` 目录
5. 在项目根目录运行 `python src/02_clean_eda.py` 验证数据可读

> 说明：kagglehub 匿名下载通道会先被尝试（`src/01_download_data.py`），
> 若成功则无需注册；失败时按上面步骤手动下载即可。

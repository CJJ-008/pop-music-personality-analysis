# -*- coding: utf-8 -*-
"""按文字描述找歌/找歌手：中文风格词典 + 音频特征检索（第 7 页「💬 描述找歌」的引擎）。

**它能做什么**：把用户的中文描述（"钢琴伴奏的深夜抒情歌""适合跑步的快节奏电子"）
解析成一组可检索的约束，再用歌曲自身的音频特征打分排序，给出匹配的歌曲与歌手，
并解释"我把你的描述理解成了什么"。

**它做不到什么**（数据边界，页面与文档都如实写明，不假装能做）：
- 描述一段**旋律**：数据集只有音频特征，没有 melody/pitch/chroma 字段，也没有音频
  文件——真正的"哼一段找歌"需要音频指纹服务（ACRCloud 等）或自建旋律库，超出本项目范围；
- 按**歌词**找歌：没有歌词文本；
- 找**男声/女声**：没有歌手性别或人声性别字段；
- **具体乐器音色**：数据集没有乐器识别，只有"原声度/器乐占比"两个近似指标，
  所以"钢琴/吉他"等词是按原声度近似，词典里逐条写明。

本模块是纯逻辑（只依赖 pandas/numpy，不依赖 Streamlit），因此：
  - src/13_style_search.py 用它导出结果表并做自检；
  - app.py 用它做运行时检索；
  - scripts/test_style_search.py 可直接单测解析与打分，不需要启动界面。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# 参与"方向"打分的特征（运行时按 style_feature_stats.csv 的基准做 z 标准化）
Z_FEATURES = ["danceability", "energy", "valence", "acousticness",
              "instrumentalness", "liveness", "speechiness", "loudness", "tempo"]

# 区间约束的衰减尺度：超出区间多远算"明显不符"（按各特征的实际量纲取）
BAND_SCALE = {"tempo": 20.0, "年份": 5.0, "时长秒": 60.0, "acousticness": 0.15,
              "instrumentalness": 0.15, "speechiness": 0.10, "liveness": 0.15,
              "valence": 0.15, "energy": 0.15, "danceability": 0.15}

FEATURE_CN = {"danceability": "舞蹈性", "energy": "能量", "valence": "情绪效价",
              "acousticness": "原声度", "instrumentalness": "器乐占比",
              "liveness": "现场感", "speechiness": "语音占比", "loudness": "响度",
              "tempo": "节奏", "时长秒": "时长", "年份": "发行年份", "mode": "调式"}

# 流派词命中的流派名（与 genre_cn 一致）；R&B 用数据里的写法
GENRES = ["说唱", "流行", "电子舞曲", "拉丁", "摇滚", "R&B"]

# ---------------------------------------------------------------- 词典 ----
# 每条： (词条, 类别, 说明, [约束...])
# 约束写法（权重可省略，默认 1.0）：
#   ("dir", 特征, ±1[, 权重])      方向：该特征高于/低于平均
#   ("band", 特征, 下限, 上限[, 权重])  区间：上下限可为 None（表示开区间）
#   ("genre", 流派名[, 权重])      流派（中文名，与 genre_cn 一致）
#   ("mode", 0/1[, 权重])         调式：1=大调 0=小调
#   ("no", 原因, 建议)            识别得出、但数据集不支持——页面会明说"这个我做不到"
# 说明列会展示给用户，凡是用近似指标的都在这里写明，不含糊。
LEXICON: list[tuple[str, str, str, list[tuple]]] = [
    # ---- 情绪与氛围 ----
    ("伤感", "情绪氛围", "情绪效价低于平均", [("dir", "valence", -1)]),
    ("悲伤", "情绪氛围", "情绪效价低于平均", [("dir", "valence", -1)]),
    ("难过", "情绪氛围", "情绪效价低于平均", [("dir", "valence", -1)]),
    ("心碎", "情绪氛围", "情绪效价低于平均", [("dir", "valence", -1)]),
    ("忧郁", "情绪氛围", "情绪效价低、小调", [("dir", "valence", -1), ("mode", 0)]),
    ("丧", "情绪氛围", "情绪效价与能量都低于平均", [("dir", "valence", -1), ("dir", "energy", -1)]),
    ("压抑", "情绪氛围", "情绪效价与能量低、小调", [("dir", "valence", -1), ("dir", "energy", -1), ("mode", 0)]),
    ("治愈", "情绪氛围", "情绪效价高于平均、能量偏低、偏原声", [("dir", "valence", 1), ("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("温暖", "情绪氛围", "情绪效价与原声度高于平均", [("dir", "valence", 1), ("dir", "acousticness", 1)]),
    ("温柔", "情绪氛围", "能量低、原声度高、情绪效价偏高", [("dir", "energy", -1), ("dir", "acousticness", 1), ("dir", "valence", 1)]),
    ("浪漫", "情绪氛围", "情绪效价高、能量低、偏原声", [("dir", "valence", 1), ("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("情歌", "情绪氛围", "情绪效价高、能量偏低", [("dir", "valence", 1), ("dir", "energy", -1)]),
    ("抒情", "情绪氛围", "能量低、原声度高", [("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("深情", "情绪氛围", "能量低、情绪效价偏高", [("dir", "energy", -1), ("dir", "valence", 1)]),
    ("开心", "情绪氛围", "情绪效价与能量高于平均", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("欢快", "情绪氛围", "情绪效价、能量、舞蹈性都高于平均", [("dir", "valence", 1), ("dir", "energy", 1), ("dir", "danceability", 1)]),
    ("快乐", "情绪氛围", "情绪效价与能量高于平均", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("阳光", "情绪氛围", "情绪效价与能量高于平均", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("正能量", "情绪氛围", "情绪效价与能量高于平均", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("甜", "情绪氛围", "情绪效价与原声度偏高", [("dir", "valence", 1), ("dir", "acousticness", 1)]),
    ("燃", "情绪氛围", "能量与响度高于平均", [("dir", "energy", 1), ("dir", "loudness", 1)]),
    ("热血", "情绪氛围", "能量与响度高于平均", [("dir", "energy", 1), ("dir", "loudness", 1)]),
    ("激昂", "情绪氛围", "能量与响度高于平均", [("dir", "energy", 1), ("dir", "loudness", 1)]),
    ("亢奋", "情绪氛围", "能量高、节奏快", [("dir", "energy", 1), ("band", "tempo", 130, None)]),
    ("上头", "情绪氛围", "能量与舞蹈性高于平均", [("dir", "energy", 1), ("dir", "danceability", 1)]),
    ("带感", "情绪氛围", "舞蹈性与能量高于平均", [("dir", "danceability", 1), ("dir", "energy", 1)]),
    ("暴躁", "情绪氛围", "能量与响度高于平均", [("dir", "energy", 1), ("dir", "loudness", 1)]),
    ("硬核", "情绪氛围", "能量与响度高于平均", [("dir", "energy", 1), ("dir", "loudness", 1)]),
    ("安静", "情绪氛围", "能量与响度低于平均", [("dir", "energy", -1), ("dir", "loudness", -1)]),
    ("宁静", "情绪氛围", "能量低、响度低、偏原声", [("dir", "energy", -1), ("dir", "loudness", -1), ("dir", "acousticness", 1)]),
    ("舒缓", "情绪氛围", "能量低、节奏慢", [("dir", "energy", -1), ("band", "tempo", None, 100)]),
    ("放松", "情绪氛围", "能量低、偏原声", [("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("助眠", "情绪氛围", "能量低、响度低、节奏慢", [("dir", "energy", -1), ("dir", "loudness", -1), ("band", "tempo", None, 100)]),
    ("催眠", "情绪氛围", "能量低、节奏慢", [("dir", "energy", -1), ("band", "tempo", None, 100)]),
    ("冥想", "情绪氛围", "能量低、器乐占比偏高", [("dir", "energy", -1), ("band", "instrumentalness", 0.3, None)]),
    ("空灵", "情绪氛围", "能量低、偏原声、器乐占比偏高", [("dir", "energy", -1), ("dir", "acousticness", 1), ("band", "instrumentalness", 0.2, None)]),
    ("氛围感", "情绪氛围", "器乐占比偏高、能量低", [("band", "instrumentalness", 0.3, None), ("dir", "energy", -1)]),
    ("梦幻", "情绪氛围", "能量低、偏原声", [("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("神秘", "情绪氛围", "小调、能量低", [("mode", 0), ("dir", "energy", -1)]),
    ("怀旧", "情绪氛围", "老歌（2000 年及以前）、偏原声", [("band", "年份", None, 2000), ("dir", "acousticness", 1)]),

    # ---- 节奏与速度（分档取自数据实测分位：25%=100、75%=134 BPM）----
    ("快歌", "节奏速度", "节奏 ≥130 BPM", [("band", "tempo", 130, None)]),
    ("快节奏", "节奏速度", "节奏 ≥130 BPM", [("band", "tempo", 130, None)]),
    ("激烈", "节奏速度", "节奏快、能量高", [("band", "tempo", 130, None), ("dir", "energy", 1)]),
    ("高能", "节奏速度", "能量高、节奏快", [("dir", "energy", 1), ("band", "tempo", 130, None)]),
    ("慢歌", "节奏速度", "节奏 ≤100 BPM", [("band", "tempo", None, 100)]),
    ("慢节奏", "节奏速度", "节奏 ≤100 BPM", [("band", "tempo", None, 100)]),
    ("慢摇", "节奏速度", "节奏偏慢、舞蹈性偏高", [("band", "tempo", None, 110), ("dir", "danceability", 1)]),
    ("中速", "节奏速度", "节奏 100~130 BPM", [("band", "tempo", 100, 130)]),
    ("蹦迪", "节奏速度", "舞蹈性、能量高，节奏 ≥120 BPM", [("dir", "danceability", 1), ("dir", "energy", 1), ("band", "tempo", 120, None)]),
    ("舞曲", "节奏速度", "舞蹈性与能量高于平均", [("dir", "danceability", 1), ("dir", "energy", 1)]),
    ("夜店", "节奏速度", "舞蹈性与能量高于平均", [("dir", "danceability", 1), ("dir", "energy", 1)]),
    ("派对", "节奏速度", "舞蹈性、能量、情绪效价都高", [("dir", "danceability", 1), ("dir", "energy", 1), ("dir", "valence", 1)]),
    ("嗨", "节奏速度", "能量与舞蹈性高于平均", [("dir", "energy", 1), ("dir", "danceability", 1)]),
    ("律动", "节奏速度", "舞蹈性高于平均", [("dir", "danceability", 1)]),
    ("摇摆", "节奏速度", "舞蹈性高于平均", [("dir", "danceability", 1)]),
    ("节奏感强", "节奏速度", "舞蹈性高、节奏偏快", [("dir", "danceability", 1), ("band", "tempo", 120, None)]),
    ("鼓点重", "节奏速度", "舞蹈性与能量高于平均", [("dir", "danceability", 1), ("dir", "energy", 1)]),

    # ---- 乐器与编制（数据集没有乐器识别，下面都是近似指标，说明里写明）----
    ("钢琴", "乐器编制", "用「原声度 ≥0.35」近似（数据集无乐器识别）", [("band", "acousticness", 0.35, None)]),
    ("吉他", "乐器编制", "用「原声度 ≥0.30」近似（数据集无乐器识别）", [("band", "acousticness", 0.30, None)]),
    ("木吉他", "乐器编制", "用「原声度 ≥0.40」近似（数据集无乐器识别）", [("band", "acousticness", 0.40, None)]),
    ("原声", "乐器编制", "原声度 ≥0.40", [("band", "acousticness", 0.40, None)]),
    ("不插电", "乐器编制", "原声度 ≥0.50、现场感偏高", [("band", "acousticness", 0.50, None), ("band", "liveness", 0.2, None)]),
    ("纯音乐", "乐器编制", "器乐占比 ≥0.50（几乎无人声）", [("band", "instrumentalness", 0.50, None)]),
    ("器乐", "乐器编制", "器乐占比 ≥0.50", [("band", "instrumentalness", 0.50, None)]),
    ("无人声", "乐器编制", "器乐占比 ≥0.50", [("band", "instrumentalness", 0.50, None)]),
    ("伴奏", "乐器编制", "器乐占比 ≥0.40", [("band", "instrumentalness", 0.40, None)]),
    ("轻音乐", "乐器编制", "器乐占比偏高、能量低", [("band", "instrumentalness", 0.40, None), ("dir", "energy", -1)]),
    ("电子", "乐器编制", "电子舞曲流派、原声度低、能量高", [("genre", "电子舞曲"), ("dir", "acousticness", -1), ("dir", "energy", 1)]),
    ("电音", "乐器编制", "电子舞曲流派、原声度低、能量高", [("genre", "电子舞曲"), ("dir", "acousticness", -1), ("dir", "energy", 1)]),
    ("合成器", "乐器编制", "原声度低、能量高（近似）", [("dir", "acousticness", -1), ("dir", "energy", 1)]),
    ("edm", "乐器编制", "电子舞曲流派", [("genre", "电子舞曲")]),
    ("弦乐", "乐器编制", "用「原声度高、器乐占比偏高」近似（无乐器识别）", [("dir", "acousticness", 1), ("band", "instrumentalness", 0.2, None)]),
    ("管弦", "乐器编制", "用「原声度高、器乐占比偏高」近似（无乐器识别）", [("dir", "acousticness", 1), ("band", "instrumentalness", 0.3, None)]),
    ("现场", "乐器编制", "现场感 ≥0.40", [("band", "liveness", 0.40, None)]),
    ("演唱会", "乐器编制", "现场感 ≥0.50", [("band", "liveness", 0.50, None)]),
    ("清唱", "乐器编制", "原声度高、器乐占比低（近似「纯人声」）", [("band", "acousticness", 0.50, None), ("band", "instrumentalness", None, 0.10)]),

    # ---- 人声与演唱 ----
    ("说唱", "人声演唱", "说唱流派、语音占比高", [("genre", "说唱"), ("band", "speechiness", 0.15, None)]),
    ("rap", "人声演唱", "说唱流派、语音占比高", [("genre", "说唱"), ("band", "speechiness", 0.15, None)]),
    ("饶舌", "人声演唱", "说唱流派、语音占比高", [("genre", "说唱"), ("band", "speechiness", 0.15, None)]),
    ("嘻哈", "人声演唱", "说唱流派、语音占比高", [("genre", "说唱"), ("band", "speechiness", 0.15, None)]),
    ("念白", "人声演唱", "语音占比高", [("band", "speechiness", 0.20, None)]),
    ("低语", "人声演唱", "语音占比偏高、能量低", [("band", "speechiness", 0.15, None), ("dir", "energy", -1)]),

    # ---- 使用场景（多特征组合，本质是"这类场景通常配什么歌"的经验映射）----
    ("健身", "使用场景", "能量高、节奏快、舞蹈性高", [("dir", "energy", 1), ("band", "tempo", 120, None), ("dir", "danceability", 1)]),
    ("跑步", "使用场景", "能量高、节奏快、舞蹈性高", [("dir", "energy", 1), ("band", "tempo", 120, None), ("dir", "danceability", 1)]),
    ("运动", "使用场景", "能量高、节奏快、舞蹈性高", [("dir", "energy", 1), ("band", "tempo", 120, None), ("dir", "danceability", 1)]),
    ("撸铁", "使用场景", "能量高、节奏快", [("dir", "energy", 1), ("band", "tempo", 120, None)]),
    ("深夜", "使用场景", "能量低、节奏偏慢、偏原声", [("dir", "energy", -1), ("band", "tempo", None, 110), ("dir", "acousticness", 1)]),
    ("睡前", "使用场景", "能量低、响度低、节奏慢", [("dir", "energy", -1), ("dir", "loudness", -1), ("band", "tempo", None, 100)]),
    ("失眠", "使用场景", "能量低、情绪效价低", [("dir", "energy", -1), ("dir", "valence", -1)]),
    ("夜晚", "使用场景", "能量低、偏原声", [("dir", "energy", -1), ("dir", "acousticness", 1)]),
    ("学习", "使用场景", "器乐占比偏高、语音占比低、能量低", [("band", "instrumentalness", 0.3, None), ("band", "speechiness", None, 0.10), ("dir", "energy", -1)]),
    ("专注", "使用场景", "器乐占比偏高、语音占比低", [("band", "instrumentalness", 0.3, None), ("band", "speechiness", None, 0.10)]),
    ("工作", "使用场景", "器乐占比偏高、能量低", [("band", "instrumentalness", 0.3, None), ("dir", "energy", -1)]),
    ("通勤", "使用场景", "舞蹈性与能量偏高", [("dir", "danceability", 1), ("dir", "energy", 1)]),
    ("开车", "使用场景", "舞蹈性、能量、情绪效价都偏高", [("dir", "danceability", 1), ("dir", "energy", 1), ("dir", "valence", 1)]),
    ("兜风", "使用场景", "情绪效价与能量偏高", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("咖啡厅", "使用场景", "原声度偏高、能量低", [("band", "acousticness", 0.30, None), ("dir", "energy", -1)]),
    ("看书", "使用场景", "原声度偏高、能量低、器乐占比偏高", [("band", "acousticness", 0.30, None), ("dir", "energy", -1), ("band", "instrumentalness", 0.2, None)]),
    ("失恋", "使用场景", "情绪效价低、偏原声", [("dir", "valence", -1), ("dir", "acousticness", 1)]),
    ("分手", "使用场景", "情绪效价低于平均", [("dir", "valence", -1)]),
    ("独处", "使用场景", "能量低、偏原声、情绪效价偏低", [("dir", "energy", -1), ("dir", "acousticness", 1), ("dir", "valence", -1)]),
    ("婚礼", "使用场景", "情绪效价高、偏原声", [("dir", "valence", 1), ("dir", "acousticness", 1)]),
    ("生日", "使用场景", "情绪效价与能量高", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("节日", "使用场景", "情绪效价与能量高", [("dir", "valence", 1), ("dir", "energy", 1)]),
    ("旅行", "使用场景", "情绪效价与舞蹈性偏高", [("dir", "valence", 1), ("dir", "danceability", 1)]),
    ("雨天", "使用场景", "能量低、情绪效价低、偏原声", [("dir", "energy", -1), ("dir", "valence", -1), ("dir", "acousticness", 1)]),
    ("午后", "使用场景", "能量低、偏原声、情绪效价偏高", [("dir", "energy", -1), ("dir", "acousticness", 1), ("dir", "valence", 1)]),

    # ---- 流派 ----
    ("拉丁", "流派", "拉丁流派", [("genre", "拉丁")]),
    ("雷鬼", "流派", "归在拉丁流派下（数据集无独立雷鬼标签）", [("genre", "拉丁")]),
    ("摇滚", "流派", "摇滚流派", [("genre", "摇滚")]),
    ("朋克", "流派", "摇滚流派、能量高（数据集无独立朋克标签）", [("genre", "摇滚"), ("dir", "energy", 1)]),
    ("金属", "流派", "摇滚流派、能量高（数据集无独立金属标签）", [("genre", "摇滚"), ("dir", "energy", 1)]),
    ("r&b", "流派", "R&B 流派", [("genre", "R&B")]),
    ("rnb", "流派", "R&B 流派", [("genre", "R&B")]),
    ("灵魂乐", "流派", "R&B 流派", [("genre", "R&B")]),
    ("蓝调", "流派", "R&B 流派（近似）", [("genre", "R&B")]),
    ("流行", "流派", "流行流派", [("genre", "流行")]),
    ("主流", "流派", "流行流派", [("genre", "流行")]),

    # ---- 年代 ----
    ("老歌", "年代", "2000 年及以前发行", [("band", "年份", None, 2000)]),
    ("经典", "年代", "2000 年及以前发行", [("band", "年份", None, 2000)]),
    ("复古", "年代", "2000 年及以前发行", [("band", "年份", None, 2000)]),
    ("80年代", "年代", "1980~1989 年发行", [("band", "年份", 1980, 1989)]),
    ("90年代", "年代", "1990~1999 年发行", [("band", "年份", 1990, 1999)]),
    ("千禧", "年代", "2001~2010 年发行", [("band", "年份", 2001, 2010)]),
    ("新歌", "年代", "2018 年及以后发行", [("band", "年份", 2018, None)]),
    ("最新", "年代", "2018 年及以后发行", [("band", "年份", 2018, None)]),
    ("近年", "年代", "2018 年及以后发行", [("band", "年份", 2018, None)]),
    ("当下", "年代", "2018 年及以后发行", [("band", "年份", 2018, None)]),

    # ---- 调式与时长 ----
    ("大调", "调式时长", "大调（明亮）", [("mode", 1)]),
    ("明亮", "调式时长", "大调、情绪效价高", [("mode", 1), ("dir", "valence", 1)]),
    ("小调", "调式时长", "小调（忧郁）", [("mode", 0)]),
    ("短歌", "调式时长", "时长 ≤3 分钟", [("band", "时长秒", None, 180)]),
    ("长歌", "调式时长", "时长 ≥5 分钟", [("band", "时长秒", 300, None)]),
    ("史诗", "调式时长", "时长 ≥5 分钟、器乐占比偏高、能量高", [("band", "时长秒", 300, None), ("band", "instrumentalness", 0.3, None), ("dir", "energy", 1)]),

    # ---- 明确不支持：识别得出，但数据集没有对应信息，页面会直说"做不到"----
    ("旋律", "不支持", "数据集没有旋律/音高信息", [("no", "数据集只有音频特征，没有旋律、音高或音符数据", "可以描述情绪、快慢、乐器感、场景等，我来按这些找")]),
    ("哼唱", "不支持", "无法按哼唱匹配", [("no", "按旋律找歌需要音频指纹服务，本项目数据里没有旋律信息", "试试用文字描述：快慢、情绪、乐器感、场景")]),
    ("歌词", "不支持", "数据集没有歌词文本", [("no", "数据集没有歌词，无法按歌词内容找歌", "可以按情绪或场景描述，例如「失恋的慢歌」")]),
    ("女声", "不支持", "数据集没有歌手性别字段", [("no", "数据集没有歌手性别或人声性别字段，无法按性别筛选", "可以按音色相关特征近似：语音占比低偏歌唱、能量高低等")]),
    ("男声", "不支持", "数据集没有歌手性别字段", [("no", "数据集没有歌手性别或人声性别字段，无法按性别筛选", "可以按能量、语音占比等特征近似描述")]),
    ("萨克斯", "不支持", "数据集没有乐器识别", [("no", "数据集没有乐器识别，只有原声度/器乐占比两个近似指标", "试试「原声」「纯音乐」「管弦」这类我可用的近似词")]),
    ("小提琴", "不支持", "数据集没有乐器识别", [("no", "数据集没有乐器识别，无法区分具体乐器", "试试「弦乐」「原声」「纯音乐」这类近似词")]),
    ("中文歌", "不支持", "数据集没有语种字段", [("no", "数据集是 Spotify 歌单数据，没有语种字段", "可以按流派、年代、情绪等描述来找")]),
    ("华语", "不支持", "数据集没有语种字段", [("no", "数据集是 Spotify 歌单数据，没有语种字段", "可以按流派、年代、情绪等描述来找")]),
    ("粤语", "不支持", "数据集没有语种字段", [("no", "数据集是 Spotify 歌单数据，没有语种字段", "可以按流派、年代、情绪等描述来找")]),
]

# 解析时要跳过的口语填充词（避免把"的/想听/给我"当成没听懂的内容）
STOPWORDS = ["的", "了", "吧", "吗", "呢", "我", "想", "要", "找", "听", "点", "来", "首", "个",
             "一些", "有点", "感觉", "风格", "歌曲", "歌", "音乐", "适合", "给我", "推荐",
             "类似", "像", "那种", "那种感觉", "稍微", "比较", "非常", "很", "特别", "帮我",
             "想要", "希望", "有没有", "什么样", "什么的", "以及", "还有", "并且", "或者",
             "一段", "一首", "那样", "这样", "这种", "一样", "曲子", "曲", "能", "可以",
             "没有", "有", "唱", "找找", "听听", "一点", "很多", "几个"]


@dataclass
class Query:
    """一次描述解析后的结果。"""
    text: str
    hits: list[tuple[str, str, str]] = field(default_factory=list)      # (词条, 类别, 说明)
    constraints: list[tuple] = field(default_factory=list)              # 展平后的约束
    unsupported: list[tuple[str, str, str]] = field(default_factory=list)  # (词条, 原因, 建议)
    unknown: list[str] = field(default_factory=list)                    # 没听懂的片段
    genres: list[str] = field(default_factory=list)                     # 命中的流派限定

    @property
    def empty(self) -> bool:
        return not self.constraints


def _normalize(text: str) -> str:
    """全角转半角、英文小写、压缩空白，便于按字面匹配。"""
    out = []
    for ch in str(text):
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return re.sub(r"\s+", "", "".join(out)).lower()


def parse_query(text: str) -> Query:
    """把中文描述解析成检索约束。

    按字面包含匹配，**长词优先**："电子舞曲"命中后不再重复命中"电子"。
    但只有被**更长**词条完整包含的短词才被屏蔽——等长的重叠词都要保留，
    否则"抒情歌"里会只剩"情歌"，丢掉"抒情"这条约束。
    """
    q = Query(text=str(text))
    t = _normalize(text)
    if not t:
        return q

    matched: list[tuple[int, int]] = []          # 已命中的 (起, 止) 区间
    for term, category, desc, cons in sorted(LEXICON, key=lambda x: -len(x[0])):
        key = _normalize(term)
        start = t.find(key)
        while start != -1:
            span = (start, start + len(key))
            covered_by_longer = any(ms <= span[0] and span[1] <= me and (me - ms) > (span[1] - span[0])
                                    for ms, me in matched)
            if not covered_by_longer:
                matched.append(span)
                if cons and cons[0][0] == "no":
                    q.unsupported.append((term, cons[0][1], cons[0][2]))
                else:
                    q.hits.append((term, category, desc))
                    q.constraints.extend(cons)
                break
            start = t.find(key, start + 1)

    q.genres = sorted({c[1] for c in q.constraints if c[0] == "genre"})
    q.unknown = _leftovers(t, matched)
    return q


def _leftovers(text: str, matched: list[tuple[int, int]]) -> list[str]:
    """挑出既没被词条命中、也不是填充词的中文片段（长度 ≥2），提示"没听懂"。"""
    hit = [False] * len(text)
    for s, e in matched:
        for i in range(s, e):
            hit[i] = True
    rest = "".join(" " if h else ch for ch, h in zip(text, hit))
    for w in STOPWORDS:
        rest = rest.replace(w, " ")
    parts = [p for p in re.split(r"[\s\W_]+", rest) if len(p) >= 2 and re.search(r"[\u4e00-\u9fff]", p)]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:6]


def constraint_reason(c: tuple, row: pd.Series, z_row: pd.Series = None) -> tuple[str, str]:
    """把一条约束在某首歌上的实际取值写成 (标签, 人话)。

    标签用于去重——多个词条常对同一特征提方向（如"深夜+抒情+情歌"都要能量低），
    解释时只保留贡献最大的一条，避免"能量低、能量低、能量低"这种复读。
    """
    kind = c[0]
    if kind == "dir":
        feat, direction = c[1], c[2]
        cn = FEATURE_CN.get(feat, feat)
        z = z_row[feat] if z_row is not None else 0
        arrow = "高" if direction > 0 else "低"
        return feat, f"{cn} {row.get(feat):.2f}（比平均{'高' if z > 0 else '低'} {abs(z):.1f}σ）"
    if kind == "band":
        feat, lo, hi = c[1], c[2], c[3]
        v = row.get(feat)
        if feat == "tempo":
            return feat, f"节奏 {v:.0f} BPM"
        if feat == "时长秒":
            return feat, f"时长 {v / 60:.1f} 分钟"
        if feat == "年份":
            return feat, f"{int(v)} 年发行"
        return feat, f"{FEATURE_CN.get(feat, feat)} {v:.2f}"
    if kind == "genre":
        return "流派", f"流派：{row.get('流派')}"
    if kind == "mode":
        return "mode", "大调" if row.get("mode") == 1 else "小调"
    return "", ""


def _constraint_score(c: tuple, df: pd.DataFrame, z: pd.DataFrame) -> np.ndarray:
    """单条约束在全部歌曲上的得分（0~1，越大越符合）。"""
    kind = c[0]
    if kind == "dir":
        feat, direction = c[1], c[2]
        return 0.5 + 0.5 * np.clip(direction * z[feat].to_numpy() / 2.0, -1, 1)
    if kind == "band":
        feat, lo, hi = c[1], c[2], c[3]
        v = df[feat].to_numpy(dtype=float)
        inside = np.ones_like(v, dtype=bool)
        if lo is not None:
            inside &= v >= lo
        if hi is not None:
            inside &= v <= hi
        dist = np.zeros_like(v)
        if lo is not None:
            dist = np.maximum(dist, np.where(v < lo, lo - v, 0.0))
        if hi is not None:
            dist = np.maximum(dist, np.where(v > hi, v - hi, 0.0))
        scale = BAND_SCALE.get(feat, 0.2)
        return np.where(inside, 1.0, np.exp(-dist / scale))
    if kind == "genre":
        return (df["流派"].to_numpy() == c[1]).astype(float)
    if kind == "mode":
        return (df["mode"].to_numpy(dtype=int) == int(c[1])).astype(float)
    return np.zeros(len(df))


def score_songs(songs: pd.DataFrame, stats: pd.DataFrame, query: Query,
                genre_strict: bool = True, popularity_alpha: float = 0.15,
                top_n: int = 10) -> pd.DataFrame:
    """按描述给歌曲打分排序。

    打分口径（可解释、可复现）：
      风格匹配分 = 各约束得分的加权平均（方向词按 z 标准化后的高低给分，
                   区间词落在区间内得满分、越远越低）；
      最终分     = (1-α) × 风格匹配分 + α × 流行度分（α=0.15，沿用项目"混合推荐"口径，
                   避免结果全是冷门歌）；
      并列时按流行度、歌名兜底排序，保证同样输入得到同样结果。

    genre_strict=True 且描述里点名了流派时，先按流派筛选候选（用户明说流派就只看该流派）。
    """
    if query.empty:
        return songs.iloc[0:0].assign(匹配分=[], 为什么=[], 风格分=[])

    df = songs
    if genre_strict and query.genres:
        df = df[df["流派"].isin(query.genres)]
        if df.empty:                      # 流派限定后没歌了，退回不限定
            df = songs
    df = df.reset_index(drop=True)

    z = (df[Z_FEATURES] - stats.loc[Z_FEATURES, "均值"]) / stats.loc[Z_FEATURES, "标准差"]

    weights = np.array([float(c[4]) if len(c) > 4 else 1.0
                        for c in query.constraints if c[0] != "no"], dtype=float)
    scores = np.vstack([_constraint_score(c, df, z)
                        for c in query.constraints if c[0] != "no"])
    style = (scores * weights[:, None]).sum(axis=0) / weights.sum()
    final = (1 - popularity_alpha) * style + popularity_alpha * (df["流行度"].to_numpy() / 100.0)

    out = df.assign(风格分=style.round(4), 匹配分=final.round(4))
    out["为什么"] = [_why(query, df.iloc[i], z.iloc[i], scores[:, i], weights) for i in range(len(df))]
    return (out.sort_values(["匹配分", "流行度", "歌曲名"], ascending=[False, False, True])
               .head(top_n).reset_index(drop=True))


def _why(query: Query, row: pd.Series, z_row: pd.Series, subscores: np.ndarray,
         weights: np.ndarray, limit: int = 3) -> str:
    """挑出贡献最大的几条约束，写成"为什么匹配"的一句话。

    多个词条对同一特征提方向时（如"深夜+抒情+情歌"都要能量低），只保留
    贡献最大的一条——解释是给人看的，不能复读。
    """
    cons = [c for c in query.constraints if c[0] != "no"]
    best: dict[str, tuple[float, str]] = {}
    for i, c in enumerate(cons):
        label, text = constraint_reason(c, row, z_row)
        if not text:
            continue
        contrib = float(subscores[i]) * float(weights[i])
        if label not in best or contrib > best[label][0]:
            best[label] = (contrib, text)
    parts = [text for _, (contrib, text)
             in sorted(best.items(), key=lambda kv: -kv[1][0])[:limit]
             if contrib > 0.05]
    return "、".join(parts) if parts else "综合特征接近你的描述"


def top_artists(scored: pd.DataFrame, pool: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """把匹配歌曲聚合到歌手：命中歌曲数越多、最高分越高越靠前。"""
    if scored.empty:
        return pd.DataFrame(columns=["歌手", "命中歌曲数", "最高匹配分", "代表歌曲"])
    g = (scored.groupby("歌手")
               .agg(命中歌曲数=("歌曲名", "size"),
                    最高匹配分=("匹配分", "max"),
                    代表歌曲=("歌曲名", "first"))
               .reset_index()
               .sort_values(["命中歌曲数", "最高匹配分", "歌手"],
                            ascending=[False, False, True]))
    return g.head(top_n).reset_index(drop=True)

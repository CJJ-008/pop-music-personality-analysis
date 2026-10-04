# -*- coding: utf-8 -*-
"""测试：按描述找歌（第 7 页「💬 描述找歌」）。

三层验证：
1. 纯逻辑：词典的方向必须写对（「助眠」能量为负、「蹦迪」舞蹈性为正…）——
   这类方向错了，界面再好看也是错的推荐；
2. 打分一致性：同样的描述必须得到同样的 Top 结果（可复现），且方向自检与
   src/13 的 sanity 互为印证；
3. AppTest 真实执行页面：描述能出结果、流派词生效、乱码给"没听懂"提示。

用法：python scripts/test_style_search.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import auth  # noqa: E402
import style_search as ss  # noqa: E402

TAB = ROOT / "outputs" / "tables"

# 登录门禁会核对「会话里的账号是否仍然有效」（被禁用/删除的账号要立刻挡下），
# 所以播种的必须是真实存在的账号——secrets 里的预置账号。
# 用虚构用户名会被当成已删除的账号拦在门外，应用什么都不会渲染。
_TEST_USER = (auth.preset_usernames() or [None])[0]
assert _TEST_USER, "本测试需要 .streamlit/secrets.toml 里至少配置一个预置账号（应用本身也依赖它）"


def test_lexicon_directions() -> None:
    """词典方向断言：写反一条就会导致整页推荐方向错误。"""
    terms = {t: dict(cons) if False else cons for t, _c, _d, cons in ss.LEXICON}
    by_term = {t: cons for t, _c, _d, cons in ss.LEXICON}

    def first_dir(term: str, feat: str) -> int:
        for c in by_term[term]:
            if c[0] == "dir" and c[1] == feat:
                return c[2]
        return 0

    cases = [
        ("助眠", "energy", -1), ("蹦迪", "danceability", 1), ("燃", "energy", 1),
        ("伤感", "valence", -1), ("开心", "valence", 1), ("慢歌", "tempo", None),
        ("快歌", "tempo", None), ("钢琴", "acousticness", None), ("纯音乐", "instrumentalness", None),
    ]
    for term, feat, want_dir in cases:
        cons = by_term[term]
        assert cons, f"词条「{term}」缺失"
        if want_dir is None:
            kinds = {c[0] for c in cons}
            assert "band" in kinds, f"「{term}」应为区间/阈值约束，实际 {kinds}"
        else:
            got = first_dir(term, feat)
            assert got == want_dir, f"「{term}」的 {feat} 方向应为 {want_dir}，实际 {got}"
    # 明确不支持：必须带原因与替代建议（页面要展示给用户）
    for term in ("旋律", "歌词", "女声"):
        cons = by_term[term]
        assert cons and cons[0][0] == "no" and len(cons[0]) >= 3, f"「{term}」应标记为不支持并带建议"
    print(f"[通过] 词典方向断言（{len(ss.LEXICON)} 个词条）")


def test_parse_and_score() -> None:
    """解析与打分：命中正确、结果可复现、方向与预期一致。"""
    matrix = pd.read_csv(TAB / "style_song_matrix.csv")
    stats = pd.read_csv(TAB / "style_feature_stats.csv", index_col=0)
    assert len(matrix) == 28356, f"歌级表应 28356 行，实际 {len(matrix)}"
    required = {"歌手", "歌曲名", "流派", "年份", "流行度", "energy", "danceability",
                "valence", "acousticness", "instrumentalness", "tempo", "mode", "时长秒"}
    assert required <= set(matrix.columns), f"歌级表缺列：{required - set(matrix.columns)}"
    assert matrix[list(required)].notna().all().all(), "歌级表存在缺失值"

    # 描述→约束：混杂描述应命中多个词条，乱码应一无所获
    q = ss.parse_query("钢琴伴奏的深夜抒情歌")
    assert {"钢琴", "深夜", "抒情"} <= {h[0] for h in q.hits}, f"命中不符：{[h[0] for h in q.hits]}"
    assert not q.unknown, f"不应有没听懂的词：{q.unknown}"
    q2 = ss.parse_query("asdfgh随便写的")
    assert q2.empty and not q2.unsupported, "乱写内容不应命中任何词条"

    # 打分方向：「蹦迪」Top10 舞蹈性均值应明显高于全体
    scored = ss.score_songs(matrix, stats, ss.parse_query("蹦迪"), top_n=10)
    assert len(scored) == 10 and scored["匹配分"].is_monotonic_decreasing, "结果应降序"
    assert scored["danceability"].mean() > matrix["danceability"].mean(), \
        f"「蹦迪」Top10 舞蹈性均值应高于全体：{scored['danceability'].mean():.3f}"
    # 可复现：同样输入 → 同样结果
    again = ss.score_songs(matrix, stats, ss.parse_query("蹦迪"), top_n=10)
    assert scored["歌曲名"].tolist() == again["歌曲名"].tolist(), "同样输入结果应可复现"
    print("[通过] 解析与打分（蹦迪 Top10 舞蹈性均值 %.3f vs 全体 %.3f）"
          % (scored["danceability"].mean(), matrix["danceability"].mean()))

    # 换描述 → 结果必须不同（防"结果写死"）
    other = ss.score_songs(matrix, stats, ss.parse_query("助眠"), top_n=10)
    assert other["歌曲名"].tolist() != scored["歌曲名"].tolist(), "不同描述结果不应相同"
    assert other["energy"].mean() < matrix["energy"].mean(), "「助眠」Top10 能量应低于全体"
    print("[通过] 换描述结果不同（助眠 Top10 能量均值 %.3f vs 全体 %.3f）"
          % (other["energy"].mean(), matrix["energy"].mean()))

    # 流派词：硬限定
    rap = ss.score_songs(matrix, stats, ss.parse_query("说唱"), top_n=10)
    assert (rap["流派"] == "说唱").all(), "描述里点名「说唱」时结果应全部为说唱"
    print("[通过] 流派限定生效（说唱）")

    # 不支持的词：解析得出、页面会明说
    q = ss.parse_query("找一段旋律")
    assert q.unsupported and q.unsupported[0][0] == "旋律", "「旋律」应标记为不支持"
    print("[通过] 不支持词正确标记（旋律）")


def test_page_render() -> None:
    """AppTest 真实执行第 7 页：出结果、解释正确、乱码有提示。"""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "tester"
    at.session_state["username"] = _TEST_USER
    at.session_state["page"] = "💬 描述找歌"
    at.run()
    assert not at.exception, f"页面抛异常：{at.exception}"
    assert len(at.text_input) >= 1, "应有搜索输入框"

    # 注意：at.run() 后控件树会重建，必须重新获取 text_input 引用再 set_value
    at.text_input(key="style_query").set_value("钢琴伴奏的深夜抒情歌")
    at.run()
    assert not at.exception, f"输入描述后抛异常：{at.exception}"
    tables = [d.value for d in at.dataframe]
    assert tables, "应渲染出匹配歌曲表"
    top = tables[0]
    assert 1 <= len(top) <= 10, f"结果行数异常：{len(top)}"
    md = "\n".join(m.value for m in at.markdown) + "\n".join(c.value for c in at.caption)
    for term in ("钢琴", "深夜", "抒情"):
        assert term in md, f"「我理解成了」区应包含「{term}」"
    print(f"[通过] 页面渲染：{len(top)} 首匹配歌曲，解释区含命中词条")

    # 乱码：给"没听懂"提示且无结果表
    at.text_input(key="style_query").set_value("asdfgh随便写的")
    at.run()
    assert not at.exception, "乱码不应抛异常"
    md = "\n".join(w.value for w in at.warning) + "\n".join(m.value for m in at.markdown)
    assert "没听懂" in md, f"乱码应提示没听懂：{md[:200]}"
    print("[通过] 乱码给出「没听懂」提示")

    # 不支持的词：明说做不到
    at.text_input(key="style_query").set_value("我想哼一段旋律找歌")
    at.run()
    assert not at.exception, "不支持词不应抛异常"
    md = "\n".join(w.value for w in at.warning)
    assert "旋律" in md and "做不到" in md, f"应明说旋律做不到：{md[:200]}"
    print("[通过] 旋律类描述明确说明做不到")


def main() -> None:
    test_lexicon_directions()
    test_parse_and_score()
    test_page_render()
    print("\n全部通过：描述找歌（词典方向 / 打分一致性 / 页面渲染）")


if __name__ == "__main__":
    main()

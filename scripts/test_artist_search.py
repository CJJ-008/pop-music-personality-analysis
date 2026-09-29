# -*- coding: utf-8 -*-
"""冒烟测试：歌手查询页能搜到人，且代表作表内容正确。

覆盖两个回归点：
1. 代表作表随查询歌手切换（表内容必须来自该歌手，不是别人或空表）；
2. 带正则符号的歌手名（A$AP Rocky / Ty Dolla $ign）按字面也能搜到
   ——str.contains 默认按正则解析，$ 会被当成行尾锚点而永远搜不到。

用法：python scripts/test_artist_search.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402


def query(name: str):
    """在歌手查询页搜索 name，返回 (页面文本, 代表作表 DataFrame)。"""
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "tester"
    at.session_state["username"] = "tester"
    at.session_state["page"] = "🔍 歌手查询"
    at.run()

    at.text_input[0].set_value(name)
    at.run()
    if at.exception:
        raise AssertionError(f"搜索「{name}」时页面抛异常：{at.exception}")
    tables = [d.value for d in at.dataframe]
    texts = ([m.value for m in at.markdown] + [w.value for w in at.warning]
             + [i.value for i in at.info])
    return "\n".join(texts), (tables[0] if tables else None)


def main() -> None:
    text, tracks = query("Ed Sheeran")
    assert tracks is not None and len(tracks) == 5, f"代表作应为 5 行，实际 {tracks}"
    assert list(tracks.columns) == ["排名", "歌曲名", "流行度", "专辑", "发行年份"], \
        f"代表作列名不符：{list(tracks.columns)}"
    assert list(tracks["排名"]) == [1, 2, 3, 4, 5], "排名应为 1~5"
    assert tracks["流行度"].is_monotonic_decreasing, "代表作应按流行度降序"
    assert "Shape of You" in set(tracks["歌曲名"]), f"Ed Sheeran 代表作缺 Shape of You：{tracks}"
    print(f"[通过] Ed Sheeran 代表作：{tracks['歌曲名'].tolist()}")

    # 换一位歌手，表必须跟着换（防止写死/串人）
    text2, tracks2 = query("Billie Eilish")
    assert set(tracks2["歌曲名"]) != set(tracks["歌曲名"]), "换歌手后代表作没变化"
    assert "bad guy" in set(tracks2["歌曲名"]), f"Billie Eilish 代表作缺 bad guy：{tracks2}"
    print(f"[通过] Billie Eilish 代表作：{tracks2['歌曲名'].tolist()}")

    # 正则元字符歌手名：必须按字面搜到
    for tricky in ("A$AP Rocky", "Ty Dolla $ign"):
        _, t = query(tricky)
        assert t is not None and len(t) == 5, f"搜不到「{tricky}」（代表作表为 {t}）"
        print(f"[通过] {tricky} 可搜到，代表作 {t['歌曲名'].tolist()[:2]}…")

    # 查不到时给提示而不是报错
    text3, _ = query("zzz_not_an_artist")
    assert "没有找到" in text3, "查不到歌手时应给出提示文案"
    print("[通过] 无匹配歌手时给出提示")

    print("\n全部通过：歌手查询页搜索 + 代表作展示正常")


if __name__ == "__main__":
    main()

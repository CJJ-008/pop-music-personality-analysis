# -*- coding: utf-8 -*-
"""冒烟测试：歌手查询页的搜索联想 + 代表作表。

覆盖三个回归点：
1. 输入几个字母就出现候选（联想），点候选即可查询——不必输入完整名字；
2. 代表作表随查询歌手切换（表内容必须来自该歌手，不是别人或空表）；
3. 带正则符号的歌手名（A$AP Rocky / Ty Dolla $ign）按字面也能搜到
   ——str.contains 默认按正则解析，$ 会被当成行尾锚点而永远搜不到。

用法：python scripts/test_artist_search.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402

# 登录门禁会核对「会话里的账号是否仍然有效」（被禁用/删除的账号要立刻挡下），
# 所以播种的必须是真实存在的账号——secrets 里的预置账号。
# 用虚构用户名会被当成已删除的账号拦在门外，应用什么都不会渲染。
_TEST_USER = (auth.preset_usernames() or [None])[0]
assert _TEST_USER, "本测试需要 .streamlit/secrets.toml 里至少配置一个预置账号（应用本身也依赖它）"


def new_page() -> AppTest:
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "tester"
    at.session_state["username"] = _TEST_USER
    at.session_state["page"] = "🔍 歌手查询"
    at.run()
    return at


def type_query(at: AppTest, text: str) -> None:
    """在搜索框输入文字（live 联想在浏览器端逐键触发，这里等价于一次输入）。"""
    box = at.text_input(key="artist_query")
    box.set_value(text)
    at.run()
    if at.exception:
        raise AssertionError(f"输入「{text}」时页面抛异常：{at.exception}")


def suggestions(at: AppTest) -> list[str]:
    """当前联想出的候选歌手（st.pills 在测试框架里是 ButtonGroup 元素）。

    必须按 key 精确取：D35 在侧边栏加了主题切换 pills 后，页面上有多个
    pills，取「第一个」会把主题切换器误当成候选列表（Ed Sheeran 唯一匹配
    的回归点就是这么误报的）。
    """
    for p in at.pills:
        if p.key == "artist_suggest":
            return list(p.options)
    return []


def tables(at: AppTest):
    return [d.value for d in at.dataframe]


def texts(at: AppTest) -> str:
    return "\n".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                     + [w.value for w in at.warning] + [i.value for i in at.info])


def main() -> None:
    # 1) 联想：输入部分名字就应给出候选，不必输入全名
    at = new_page()
    type_query(at, "justin")
    cands = suggestions(at)
    assert cands, f"输入「justin」应联想出候选，实际为空：{texts(at)[:200]}"
    assert any("Justin" in c for c in cands), f"候选里应有 Justin 系列：{cands}"
    print(f"[通过] 输入「justin」联想出 {len(cands)} 位候选：{cands[:3]}…")

    # 2) 点候选即可查询（不必输入完整名字）
    at.pills[0].select(cands[0])
    at.run()
    assert not at.exception, f"点击候选后抛异常：{at.exception}"
    tracks = tables(at)[0]
    assert len(tracks) == 5, f"代表作应为 5 行，实际 {tracks}"
    assert list(tracks.columns) == ["排名", "歌曲名", "流行度", "专辑", "发行年份"], \
        f"代表作列名不符：{list(tracks.columns)}"
    assert list(tracks["排名"]) == [1, 2, 3, 4, 5], "排名应为 1~5"
    assert tracks["流行度"].is_monotonic_decreasing, "代表作应按流行度降序"
    print(f"[通过] 点候选「{cands[0]}」直接出画像，代表作：{tracks['歌曲名'].tolist()[:2]}…")

    # 3) 唯一匹配自动选中（输入到只剩一个候选时无需点击）
    at = new_page()
    type_query(at, "Ed Sheeran")
    tracks = tables(at)[0]
    assert "Shape of You" in set(tracks["歌曲名"]), f"Ed Sheeran 代表作缺 Shape of You：{tracks}"
    assert not suggestions(at), "唯一匹配时不应再显示候选列表"
    print("[通过] 唯一匹配自动选中（Ed Sheeran）")

    # 4) 换一位歌手，表必须跟着换（防止写死/串人）
    at = new_page()
    type_query(at, "Billie Eilish")
    names = set(tables(at)[0]["歌曲名"])
    assert "bad guy" in names, f"Billie Eilish 代表作缺 bad guy：{names}"
    print(f"[通过] Billie Eilish 代表作：{sorted(names)[:2]}…")

    # 5) 正则元字符歌手名：必须按字面搜到（$ 不能被当成行尾锚点）
    at = new_page()
    type_query(at, "A$AP")
    cands = suggestions(at)
    assert len(cands) >= 2, f"「A$AP」应联想出多位候选（$ 不能当正则解析）：{cands}"
    print(f"[通过] 「A$AP」联想出：{cands}")

    at = new_page()
    type_query(at, "Ty Dolla $")     # 唯一匹配 → 自动选中，不出候选列表
    assert "Ty Dolla" in texts(at), f"「Ty Dolla $」应唯一匹配到 Ty Dolla $ign：{texts(at)[:200]}"
    assert len(tables(at)[0]) == 5, "唯一匹配后应直接出代表作表"
    print("[通过] 「Ty Dolla $」唯一匹配自动选中")

    # 6) 查不到时给提示而不是报错
    at = new_page()
    type_query(at, "zzz_not_an_artist")
    assert "没有找到" in texts(at), "查不到歌手时应给出提示文案"
    print("[通过] 无匹配歌手时给出提示")

    print("\n全部通过：搜索联想 + 代表作展示正常")


if __name__ == "__main__":
    main()

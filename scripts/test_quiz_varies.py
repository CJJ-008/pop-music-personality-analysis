# -*- coding: utf-8 -*-
"""回归测试：性格小测评的结果必须随作答变化（防 z_ 前缀对齐 bug 复发）。

用法：python scripts/test_quiz_varies.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402

SCALE = ["1 完全不同意", "2 比较不同意", "3 一般", "4 比较同意", "5 完全同意"]

# 登录门禁会核对「会话里的账号是否仍然有效」（被禁用/删除的账号要立刻挡下），
# 所以播种的必须是真实存在的账号——secrets 里的预置账号。
# 用虚构用户名会被当成已删除的账号拦在门外，应用什么都不会渲染。
_TEST_USER = (auth.preset_usernames() or [None])[0]
assert _TEST_USER, "本测试需要 .streamlit/secrets.toml 里至少配置一个预置账号（应用本身也依赖它）"


def run_quiz(picks: list[int], resubmit: bool = True) -> str:
    """用给定的 25 题作答跑一遍测评页，返回结果区文本。

    resubmit=True 时再改一次答案重新提交——这一步专门覆盖
    「提交后 index 回填越界」的崩溃路径（历史 bug）。
    """
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    # 跳过登录门禁
    at.session_state["authentication_status"] = True
    at.session_state["name"] = "tester"
    at.session_state["username"] = _TEST_USER
    at.session_state["page"] = "📝 性格小测评"
    at.run()

    def fill_and_submit(values: list[int]) -> None:
        radios = at.radio
        assert len(radios) == 25, f"题目数量应为 25，实际 {len(radios)}"
        for r, pick in zip(radios, values):
            r.set_value(SCALE[pick - 1])
        at.run()
        for b in at.button:
            if "提交" in b.label:
                b.click()
                break
        at.run()
        if at.exception:
            raise AssertionError(f"页面抛异常：{at.exception}")

    fill_and_submit(picks)
    if resubmit:
        # 第二次提交：此时 quiz_saved 已有值，index 回填路径被触发
        flipped = [6 - p for p in picks]
        fill_and_submit(flipped)
        picks = flipped

    texts = [m.value for m in at.markdown] + [s.value for s in at.success]
    return "\n".join(texts), picks


def readout(text: str) -> str:
    """只取「你的五维得分」解读行，忽略名词小课堂等无关文案。"""
    lines = [ln for ln in text.splitlines()
             if "标准差" in ln and ln.strip().startswith("-")]
    return "\n".join(lines)


def main() -> int:
    n = 25
    low, low_picks = run_quiz([1] * n)
    high, high_picks = run_quiz([5] * n)
    mixed, mixed_picks = run_quiz([5, 1, 3, 5, 2] * 5)

    ok = True
    if readout(low) == readout(high):
        print("✗ 两套极端作答结果完全相同 —— 结果没有随作答变化")
        ok = False
    else:
        print("✓ 两套极端作答：结果不同")
    if readout(low) == readout(mixed):
        print("✗ 混合作答与极端作答结果相同")
        ok = False
    else:
        print("✓ 混合作答与极端作答：结果不同")
    if ok:
        print("✓ 提交后改答案重交未崩溃（index 回填路径）")

    for name, txt, picks in [("作答 A", low, low_picks),
                             ("作答 B", high, high_picks),
                             ("作答 C", mixed, mixed_picks)]:
        uniq = sorted(set(picks))
        print(f"\n--- {name}（最终答案 {uniq}，重交后）的五维解读 ---")
        print(readout(txt))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

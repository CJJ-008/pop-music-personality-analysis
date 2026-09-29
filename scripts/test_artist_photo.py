# -*- coding: utf-8 -*-
"""歌手照片模块测试：名字比对纯逻辑 + 实际取图。

联网部分按图源降级链实测（Spotify 未配置凭据时走网易云兜底）。
网易云接口有频率限制（超限时返回 code 405「操作频繁」），遇到限流时
联网断言自动跳过（退出码 0）——照片是锦上添花的功能，限流不该判测试失败。

用法：python scripts/test_artist_photo.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from artist_photo import _name_matches, get_artist_photo  # noqa: E402


def test_name_matching() -> None:
    """名字比对：只认归一化后指向同一歌手的候选，防止张冠李戴。"""
    cases = [
        ("Ed Sheeran", "Ed Sheeran", True),
        ("ed sheeran", "Ed Sheeran", True),             # 大小写/空格不敏感
        ("Ed Sheeran (musician)", "Ed Sheeran", True),  # 消歧后缀可剥离
        ("$uicideBoy$", "$uicideBoy$", True),           # 符号名
        ("Ty Dolla $ign", "Ty Dolla $ign", True),
        ("Taylor Swift", "Ed Sheeran", False),          # 别人
        ("Ed", "Ed Sheeran", False),                    # 子串不算
        ("Ed Sheeran's greatest", "Ed Sheeran", False),
        ("", "Ed Sheeran", False),
    ]
    for cand, query, want in cases:
        got = _name_matches(cand, query)
        assert got == want, f"_name_matches({cand!r}, {query!r}) 应为 {want}，实际 {got}"
    print(f"[通过] 名字比对 {len(cases)} 组用例")


def netease_throttled() -> bool:
    """网易云当前是否处于限流状态（code 405）。"""
    try:
        r = requests.get("https://music.163.com/api/search/get/web", timeout=8,
                         params={"s": "Ed Sheeran", "type": 100, "limit": 1},
                         headers={"User-Agent": "Mozilla/5.0",
                                  "Referer": "https://music.163.com/"})
        return r.json().get("code") == 405
    except Exception:
        return False


def test_live_fetch() -> None:
    """实际取图：热门歌手必有照片；查无此人必须返回 None（宁缺勿错）。"""
    for name in ["Ed Sheeran", "Billie Eilish", "$uicideBoy$"]:
        photo = get_artist_photo(name)
        assert photo is not None, f"「{name}」应能取到照片"
        assert photo["url"].startswith("http"), f"照片地址异常：{photo}"
        assert photo["provider"] in ("Spotify 官方", "网易云音乐"), f"未知图源：{photo}"
        assert photo["source_url"].startswith("http"), f"图源链接异常：{photo}"
        print(f"[通过] {name} -> {photo['provider']}（{photo['url'][:60]}…）")

    assert get_artist_photo("zzz not an artist") is None, "查无此人时应返回 None"
    print("[通过] 查无此人返回 None（宁缺勿错）")


def main() -> None:
    test_name_matching()
    if netease_throttled():
        print("[跳过] 网易云接口正处于限流状态（code 405），联网取图断言跳过；"
              "稍后重跑即可。若经常需要离线/高频率使用，建议配置 Spotify 官方图源。")
    else:
        test_live_fetch()
    print("\n全部通过：歌手照片模块正常")


if __name__ == "__main__":
    main()

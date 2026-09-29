# -*- coding: utf-8 -*-
"""歌手照片：为「歌手查询」页取歌手头像，图源按「官方优先」自动降级。

图源顺序（前者不可用就换后者，都不可用则返回 None，页面显示占位提示）：
  1. **Spotify 官方 API** —— 需在 st.secrets 配置 [spotify] client_id / client_secret
     （免费注册一个 App 即可，约 2 分钟）。图片来自官方 CDN，与项目数据集同源；
  2. **网易云音乐免密钥接口** —— 无需任何配置的兜底图源（非官方接口，可能变更或限流）。

两条硬规则（都是为了「别张冠李戴」和「别拖垮页面」）：
  - **只认名字对得上的候选**：检索结果与歌手名做归一化精确比对（忽略大小写、
    空格与标点），对不上就当作没找到——宁可不显示照片，也不能显示别人的照片；
  - **照片是锦上添花，不能影响页面**：本模块对外的 get_artist_photo() 永不抛异常，
    断网、超时、被限流、未配置凭据都只返回 None；缓存语义区分「确认查无此人」
    （可缓存）与「请求没成功」（不缓存，下次查询自动重试），避免一次网络抖动
    变成 24 小时没照片。

exe 打包时本文件需与 app.py 一同作为数据文件进包（见 streamlit_app.spec）。
"""
import re

import requests
import streamlit as st

TIMEOUT = 6  # 单次请求超时（秒）：照片是加分项，宁可放弃也不要卡住页面

# 图片尺寸：够清晰又不至于拖慢页面（Spotify 给的是 640/300/64 三档）
TARGET_IMAGE_WIDTH = 320


def _norm(name: str) -> str:
    """归一化歌手名：只保留字母数字，用于宽松比对。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(name).lower())


def _name_matches(candidate: str, query: str) -> bool:
    """候选名与查询名是否指向同一位歌手。

    允许维基/接口常见的消歧后缀，如 "Ed Sheeran (musician)"、"Lane 8 (DJ)"。
    """
    cand, want = _norm(candidate), _norm(query)
    if not cand or not want:
        return False
    if cand == want:
        return True
    # 去掉括号内容后再比一次（"X (band)" -> "X"）
    return _norm(re.sub(r"[\(（\[].*?[\)）\]]", "", str(candidate))) == want


def _pick_image(images: list) -> str | None:
    """从接口返回的图片列表里挑一张尺寸合适的（优先 ≥ 目标宽度的最小一张）。"""
    usable = [i for i in images or [] if i.get("url")]
    if not usable:
        return None
    big_enough = [i for i in usable if (i.get("width") or 0) >= TARGET_IMAGE_WIDTH]
    return min(big_enough, key=lambda i: i.get("width") or 0)["url"] if big_enough \
        else max(usable, key=lambda i: i.get("width") or 0)["url"]


def _spotify_credentials() -> tuple[str, str] | None:
    """读取 Spotify 凭据；未配置或仍是占位值则返回 None。"""
    try:
        conf = st.secrets["spotify"]
        cid, secret = str(conf.get("client_id", "")), str(conf.get("client_secret", ""))
    except Exception:
        return None
    if not cid or not secret or "REPLACE" in cid.upper() or "REPLACE" in secret.upper():
        return None
    return cid, secret


@st.cache_data(ttl=3000, show_spinner=False)  # 官方令牌有效期 1 小时，缓存 50 分钟
def _spotify_token() -> str | None:
    """换官方访问令牌；凭据未配置返回 None（跳过该图源），请求失败抛异常。"""
    creds = _spotify_credentials()
    if not creds:
        return None
    r = requests.post("https://accounts.spotify.com/api/token", timeout=TIMEOUT,
                      data={"grant_type": "client_credentials"}, auth=creds)
    r.raise_for_status()
    return r.json().get("access_token")


def _from_spotify(name: str) -> dict | None:
    """Spotify 官方 API：搜索歌手，取官方头像。

    凭据未配置返回 None（跳过该图源）；请求失败抛异常（不缓存本次结论）。
    """
    token = _spotify_token()
    if not token:
        return None
    r = requests.get("https://api.spotify.com/v1/search", timeout=TIMEOUT,
                     params={"q": name, "type": "artist", "limit": 5},
                     headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    for item in r.json().get("artists", {}).get("items", []):
        if not _name_matches(item.get("name", ""), name):
            continue
        url = _pick_image(item.get("images"))
        if url:
            return {"url": url, "provider": "Spotify 官方",
                    "source_url": (item.get("external_urls") or {}).get("spotify")}
    return None


def _from_netease(name: str) -> dict | None:
    """网易云音乐免密钥接口（兜底）：搜索歌手，取用户上传头像。

    请求失败（含限流 code 405）抛异常；返回 None 表示接口正常但没这位歌手。
    """
    r = requests.get("https://music.163.com/api/search/get/web", timeout=TIMEOUT,
                     params={"s": name, "type": 100, "limit": 10},
                     headers={"User-Agent": "Mozilla/5.0",
                              "Referer": "https://music.163.com/"})
    r.raise_for_status()
    for item in r.json().get("result", {}).get("artists") or []:
        if not _name_matches(item.get("name", ""), name):
            continue
        pic = item.get("picUrl")
        if pic:
            return {"url": f"{pic}?param={TARGET_IMAGE_WIDTH * 2}y{TARGET_IMAGE_WIDTH * 2}",
                    "provider": "网易云音乐",
                    "source_url": f"https://music.163.com/#/artist?id={item.get('id')}"}
    return None


def get_artist_photo(name: str) -> dict | None:
    """取歌手照片：Spotify 官方优先，网易云兜底；都没有则返回 None。

    返回 {"url": 图片地址, "provider": 图源名, "source_url": 图源页面}。
    缓存语义（关键设计，防止一次网络抖动变成“永远没照片”）：
      - 成功结果缓存 24 小时；
      - 两家都**正常响应**但确认没这位歌手 → 缓存否定结论 24 小时；
      - 请求异常（断网/超时/被限流）→ 本次返回 None 但**不缓存**，下次查询自动重试。
    """
    try:
        return _photo_cached(name)
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner="正在获取歌手照片…")
def _photo_cached(name: str) -> dict | None:
    """带缓存的取图：只让「确定的结果」进缓存，瞬时异常直接抛出。

    返回 None 表示两家图源都正常响应且确认查无此人（这个否定结论可以缓存）；
    抛异常表示至少一家因网络/限流等原因没能完成查询（这个不能缓存）。
    """
    errors: list[Exception] = []
    for fetch in (_from_spotify, _from_netease):
        try:
            photo = fetch(name)
        except Exception as e:
            errors.append(e)  # 这一家的结论不可信，先记下，看下一家
            continue
        if photo is not None:
            return photo
    if errors:
        raise errors[0]  # 有请求没成功 → 结论不可信，抛出（不缓存，下次重试）
    return None          # 两家都正常响应且都没有 → 确认查无此人（可缓存）

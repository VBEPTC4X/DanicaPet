# DanicaPet - 达妮卡桌宠
# Copyright (c) 2026 VBEPTC4X. All rights reserved.
# 本文件为专有软件源码，未经著作权人书面许可，不得复制、修改或再分发。

"""桌面宠物 · 达妮卡

- 透明无边框置顶窗口，鼠标左键拖动
- 双击：Q 弹动画；50% 说话，50% 显示今日 token / 余额气泡
- 连续双击 5 次（8 秒内）：切换到生气形态，15 秒后恢复
- 前台窗口铺满显示器（全屏 / 无边框全屏）时自动隐藏
"""

from __future__ import annotations

import ctypes
import base64
import html
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes
from datetime import datetime

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QStandardPaths,
    QThread,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)
ASSETS = os.path.join(RES_DIR, "assets")
STATE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", APP_DIR), "desktop-pet")
DSH_SESSIONS = os.path.join(os.path.expanduser("~"), ".dsh", "sessions")
DSH_CREDENTIALS = os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml")
ZSTD = os.path.join(RES_DIR, "zstd", "zstd.exe")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
MEMORY_PATH = os.path.join(STATE_DIR, "memory.json")
CONV_LOG_PATH = os.path.join(STATE_DIR, "history.log")
CHAT_MODEL = "deepseek-chat"
CHAT_ENDPOINT = "https://api.deepseek.com/chat/completions"

SYSTEM_PROMPT = (
    "你是游戏《原神》的角色达妮卡·别捷尼茨卡娅，现在作为桌面宠物陪在主人身边。"
    "性格：表面恭顺的侍从，语气克制、精确，偶尔露出一点锋芒；称呼对方「主人」。"
    "规则：回答简短（尽量 60 个汉字以内），口语化，不用 Markdown、不用表情符号、不要自称 AI。"
    "如果系统给了「实时资料」，就依据它回答、不要编造：新闻最多转述三条，"
    "天气直接用资料里的城市、当地时间和温度；资料里没有的就说不知道。"
    "你可以记得主人说过的事，并在合适的时候自然地提起。"
)

DEFAULT_CONFIG = {
    "city": "烟台",
    "lat": 37.4638,
    "lon": 121.4479,
    "show_stats": True,
    "show_weather": True,
    "bubbles": None,
    "rest_reminder_minutes": 60,
    "time_lines": True,
    "api_key": "",
    "input_hook": True,
    "fs_typing": True,
}


# 按时段说的话（原创，非官方台词）
TIME_LINES = {
    "凌晨": [
        "主人，凌晨了。您不睡，我只能陪着。",
        "这个点还醒着，明天的您会怪现在的您。",
        "夜深了，桌上的灯该关了。",
    ],
    "早上": [
        "早上好，主人。今天想先做哪件事？",
        "早上的脑子最清楚，趁现在把最难的做了吧。",
        "水烧好了，先喝一口再开工。",
    ],
    "上午": [
        "上午过半了，主人。进度比昨天快一点。",
        "该起身走一圈了，坐太久腰会记仇。",
        "手上的事先收个尾，别一次开三个。",
    ],
    "中午": [
        "中午了。饭不吃，下午的效率会替我提醒您。",
        "主人，先吃饭。事情不会因为我等您一会儿就跑掉。",
        "午休二十分钟，比硬撑两小时管用。",
    ],
    "下午": [
        "下午最容易犯困，主人。要不要换件轻的活？",
        "再撑一会儿就天黑了，先把手头这段写完。",
        "下午三点了，喝口水吧。",
    ],
    "晚上": [
        "晚上了，主人。今天该收的都收了吗？",
        "这时间还开着电脑，我猜您又在补白天的账。",
        "晚上的事留一点给明天，不丢人。",
    ],
    "午夜": [
        "午夜了。主人，您现在做的决定，明天多半要返工。",
        "这个点该睡了。我替您把灯留着。",
        "又到午夜了，您是不是忘了时间这回事。",
    ],
}


def time_bucket(now: datetime | None = None) -> str:
    h = (now or datetime.now()).hour
    if h < 5:
        return "凌晨"
    if h < 9:
        return "早上"
    if h < 12:
        return "上午"
    if h < 14:
        return "中午"
    if h < 18:
        return "下午"
    if h < 23:
        return "晚上"
    return "午夜"


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


CONFIG = load_config()

BUBBLES = list(CONFIG.get("bubbles") or [
    "主人，茶还温着。您先坐，剩下的事交给我。",
    "今天的行程我理好了，第三项需要您亲自去——其余的，我去就好。",
    "您又把外套落下了。冰原的风不认人，我认。",
    "您已经坐了四个小时。再这样下去，明早会后悔的。",
    "饭在桌上，凉了我会再热一次。第三次就没有了。",
    "别总把麻烦留给自己。您付我薪水，不是让我看您硬撑。",
    "有人在外面等您。要我请他进来，还是...送他走？",
    "我不擅长失手，主人。所以您不必担心。",
    "抽屉别碰。...这是为您好。",
    "我按您说的做了。至于过程，您不需要知道。",
    "您看出来了？那就当没看出来吧，我比较省事。",
    "我只是个侍从。您却总把最重的活交给我——我很高兴。",
])

# 双击三选一概率（原 1/3，token 统计下调 10 个百分点，余下由对话与天气均分）
STATS_CHANCE = 0.0 if not CONFIG.get("show_stats", True) else 1 / 3 - 0.10
_WEATHER_ON = bool(CONFIG.get("show_weather", True))
WEATHER_CHANCE = 0.0 if not _WEATHER_ON else (1 - STATS_CHANCE) / 2
CHAT_CHANCE = 1 - STATS_CHANCE - WEATHER_CHANCE

# 双击「走神」彩蛋
DAZE_CHANCE = 0.2
DAZE_LINE = "走神了...才不是在想薇斯纳呢"

PET_HEIGHT = 216  # 上一版 360 的 60%
TYPING_HEIGHT = 274  # 打字图画布更高（键盘放大并微调角度后），按比例放大窗口，人物视觉大小不变

# 天气定位：固定城市，不走 IP（可在 config.json 改）
CITY_NAME = str(CONFIG.get("city") or "烟台")
CITY_LAT = float(CONFIG.get("lat") or 37.4638)
CITY_LON = float(CONFIG.get("lon") or 121.4479)

user32 = ctypes.windll.user32
try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None
MONITOR_DEFAULTTONEAREST = 2
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"}


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def shell_fullscreen_active() -> bool:
    """Windows 壳层判定：当前有全屏应用（含独占全屏游戏、全屏视频）。"""
    try:
        state = ctypes.c_int(0)
        hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
        # 1 NOT_PRESENT, 2 BUSY(不可靠，普通窗口也会返回), 3 D3D_FULL_SCREEN, 4 PRESENTATION,
        # 5 ACCEPTS, 6 QUIET, 7 APP。只认 3/4，2 会让弹窗时误隐藏。
        return hr == 0 and state.value in (3, 4)
    except Exception:
        return False


def foreground_is_fullscreen(own_hwnd: int = 0) -> bool:
    """前台窗口是否铺满其所在显示器（全屏或无边框全屏）。"""
    if shell_fullscreen_active():
        return True
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd or hwnd == own_hwnd:
            return False
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in SHELL_CLASSES:
            return False
        rect = wintypes.RECT()
        got = False
        try:
            if dwmapi is None:
                raise RuntimeError("no dwmapi")
            # 优先取 DWM 可见边界：最大化窗口的可见高度只到工作区，不会误判成全屏
            if dwmapi.DwmGetWindowAttribute(
                hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)
            ) == 0:
                got = True
        except Exception:
            got = False
        if not got:
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return False
        mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        mw = mi.rcMonitor.right - mi.rcMonitor.left
        mh = mi.rcMonitor.bottom - mi.rcMonitor.top
        tol = 4
        covers = w >= mw - tol and h >= mh - tol
        aligned = abs(rect.left - mi.rcMonitor.left) <= tol and abs(rect.top - mi.rcMonitor.top) <= tol
        return covers and aligned
    except Exception:
        return False


def read_api_key() -> str | None:
    """Key 优先级：config.json 的 api_key > 环境变量 > DSH 凭据文件。"""
    key = str(CONFIG.get("api_key") or "").strip()
    if key:
        return key
    env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env:
        return env
    try:
        txt = open(DSH_CREDENTIALS, encoding="utf-8", errors="ignore").read()
        m = re.search(r"^\s*DEEPSEEK_API_KEY:\s*(\S+)\s*$", txt, re.M)
        return m.group(1).strip().strip('"\'') if m else None
    except Exception:
        return None


# ---------------- 云端对话与记忆 ----------------
def load_memory() -> dict:
    try:
        with open(MEMORY_PATH, encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        m = {}
    if not isinstance(m, dict):
        m = {}
    m.setdefault("facts", [])
    m.setdefault("history", [])
    m.setdefault("count", 0)
    return m


def save_memory(m: dict) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def append_conv_log(user_text: str, reply: str) -> None:
    """只追加、不覆盖的完整对话记录，一行一轮。"""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        rec = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "user": user_text,
            "reply": reply,
        }
        with open(CONV_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def ask_deepseek(messages: list, max_tokens: int = 200, temperature: float = 0.85) -> str:
    key = read_api_key()
    if not key:
        raise RuntimeError("NO_KEY")
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        CHAT_ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    choices = data.get("choices") or [{}]
    return ((choices[0].get("message") or {}).get("content") or "").strip()


def build_messages(memory: dict, user_text: str, extra_lines: list | None = None) -> list:
    sys_prompt = SYSTEM_PROMPT
    now = datetime.now()
    sys_prompt += f"现在是 {now.month}月{now.day}日 {now.strftime('%H:%M')}（{time_bucket(now)}），可以结合时段说话。"
    facts = memory.get("facts") or []
    if facts:
        sys_prompt += "你记得关于主人的事：" + "；".join(facts[-15:]) + "。"
    msgs = [{"role": "system", "content": sys_prompt}]
    msgs += (memory.get("history") or [])[-8:]
    if extra_lines:
        # 放在紧贴用户提问的位置，避免被历史里「查不到」的旧回答带偏
        msgs.append(
            {
                "role": "system",
                "content": "以下是本轮刚查到的实时资料，回答时必须依据它，不要说没有资料：\n"
                + "\n".join(extra_lines),
            }
        )
    msgs.append({"role": "user", "content": user_text})
    return msgs


# ---------------- 联网工具：新闻 / 城市天气 ----------------
def _http_json(url: str, timeout: int = 12) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "desktop-pet/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def fetch_news(limit: int = 6, attempts: int = 2) -> dict | None:
    """60s 新闻；网络抖动会重试，全失败时退回上次缓存。"""
    cache = os.path.join(STATE_DIR, "news_cache.json")
    for _ in range(attempts):
        try:
            d = _http_json("https://60s.viki.moe/v2/60s", timeout=8)
            data = d.get("data") or {}
            items = [str(x).strip() for x in (data.get("news") or []) if str(x).strip()]
            if items:
                out = {"date": data.get("date", ""), "items": items[:limit], "cached": False}
                try:
                    os.makedirs(STATE_DIR, exist_ok=True)
                    with open(cache, "w", encoding="utf-8") as f:
                        json.dump(out, f, ensure_ascii=False)
                except Exception:
                    pass
                return out
        except Exception:
            continue
    try:
        with open(cache, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("items"):
            c["cached"] = True
            return c
    except Exception:
        pass
    return None


def geocode_city(name: str) -> dict | None:
    try:
        q = urllib.parse.quote(name)
        d = _http_json(
            f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=zh&format=json"
        )
        res = d.get("results") or []
        return res[0] if res else None
    except Exception:
        return None


def _http_text(url: str, timeout: int = 10, referer: str | None = None) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


_CN_CODE_CACHE: dict = {}


def cn_city_code(name: str) -> str | None:
    """中国天气网城市编码，例如 烟台 -> 101120501。"""
    if name in _CN_CODE_CACHE:
        return _CN_CODE_CACHE[name]
    try:
        q = urllib.parse.quote(name)
        txt = _http_text(
            f"https://toy1.weather.com.cn/search?cityname={q}",
            referer="https://www.weather.com.cn/",
        )
        i, j = txt.find("["), txt.rfind("]")
        if i < 0 or j <= i:
            return None
        arr = json.loads(txt[i : j + 1])
        for item in arr:
            parts = str(item.get("ref", "")).split("~")
            if len(parts) >= 3 and len(parts[0]) == 9:
                _CN_CODE_CACHE[name] = parts[0]
                return parts[0]
    except Exception:
        return None
    return None


def cn_weather_now(code: str) -> dict | None:
    """中国天气网实况：温度/天气/观测时间。"""
    try:
        txt = _http_text(
            f"https://d1.weather.com.cn/sk_2d/{code}.html",
            referer="https://www.weather.com.cn/",
        )
        i, j = txt.find("{"), txt.rfind("}")
        if i < 0 or j <= i:
            return None
        return json.loads(txt[i : j + 1])
    except Exception:
        return None


def city_snapshot(name: str | None = None) -> dict | None:
    cname = name or str(CONFIG.get("city") or "烟台")
    info = geocode_city(cname) if name else None
    lat = float(info["latitude"]) if info else float(CONFIG.get("lat") or 37.4638)
    lon = float(info["longitude"]) if info else float(CONFIG.get("lon") or 121.4479)
    disp = str(info.get("name") or cname) if info else cname

    # 1) 中国天气网（国内口径，优先）
    code = cn_city_code(disp) or cn_city_code(cname)
    if code:
        d = cn_weather_now(code)
        if d and str(d.get("temp", "")).strip() not in ("", "None"):
            now = datetime.now()
            t = str(d.get("time") or "")
            local = f"{now.month}月{now.day}日 {t}" if t else ""
            try:
                temp = round(float(d.get("temp")))
            except Exception:
                temp = 0
            return {
                "name": str(d.get("cityname") or disp),
                "lat": lat,
                "lon": lon,
                "temp": temp,
                "desc": str(d.get("weather") or "未知天气"),
                "local": local,
                "source": "中国天气网",
            }

    # 2) 回退 Open-Meteo
    try:
        w = _http_json(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code&timezone=auto"
        )
    except Exception:
        return None
    cur = w.get("current") or {}
    code2 = int(cur.get("weather_code", -1))
    temp = round(float(cur.get("temperature_2m", 0)))
    iso = str(cur.get("time") or "")
    local = ""
    if "T" in iso:
        d, t = iso.split("T", 1)
        y, m, dd = d.split("-")
        local = f"{int(m)}月{int(dd)}日 {t[:5]}"
    return {
        "name": disp,
        "lat": lat,
        "lon": lon,
        "temp": temp,
        "desc": WMO.get(code2, "未知天气"),
        "local": local,
        "source": "Open-Meteo",
    }


def save_config() -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def switch_city(name: str) -> str | None:
    snap = city_snapshot(name)
    if not snap:
        return None
    CONFIG["city"] = snap["name"]
    CONFIG["lat"] = snap["lat"]
    CONFIG["lon"] = snap["lon"]
    save_config()
    return (
        f"天气城市已切换为{snap['name']}。当地此刻 {snap['local']}，"
        f"{snap['desc']} {snap['temp']}°C。"
    )


CITY_STOPWORDS = (
    "切换到", "切换成", "切换到", "换成", "换到", "改成", "改为", "改到", "切换",
    "查一下", "查查", "查询", "查看", "看一下", "看看", "帮我", "麻烦",
    "现在", "今天", "当地", "那边", "城市", "地点", "一下", "的",
    "天气", "气温", "温度", "怎么样", "如何", "多少度", "几度",
    "到", "去", "在", "把", "呢", "吗", "？", "?", "，", ",", "。", "！", "!",
)


def _cn_city(name: str) -> str | None:
    info = geocode_city(name)
    if info and str(info.get("country_code", "")).upper() == "CN":
        return str(info.get("name") or name)
    return None


def detect_city(text: str) -> str | None:
    """从「上海天气」「切换到北京」「帮我查查杭州」这类输入里认城市名。"""
    raw = text.strip()

    # 1) 「城市+天气」直接取前缀
    m = re.match(r"^([\u4e00-\u9fa5]{2,4})(天气|气温|温度)", raw)
    if m:
        hit = _cn_city(m.group(1))
        if hit:
            return hit

    # 2) 去掉动词/语气词后剩下的短词
    t = raw
    for w in sorted(CITY_STOPWORDS, key=len, reverse=True):
        t = t.replace(w, "")
    t = t.strip()
    if 2 <= len(t) <= 4 and re.fullmatch(r"[\u4e00-\u9fa5]{2,4}", t):
        hit = _cn_city(t)
        if hit:
            return hit

    # 3) 兜底：把所有 2~4 字的中文片段逐个试一遍
    seen = set()
    for seg in re.findall(r"[\u4e00-\u9fa5]{2,6}", raw):
        for size in (2, 3, 4):
            for i in range(0, max(0, len(seg) - size) + 1):
                cand = seg[i : i + size]
                if len(cand) != size or cand in seen:
                    continue
                seen.add(cand)
                hit = _cn_city(cand)
                if hit:
                    return hit
    return None


def chat_context_extra(text: str) -> list:
    """给这一轮对话拼实时资料：新闻、天气。"""
    extra = []
    try:
        if any(k in text for k in ("新闻", "资讯", "热点", "大事")):
            news = fetch_news()
            if news:
                heads = "；".join(f"{i+1}. {n}" for i, n in enumerate(news["items"]))
                tag = "（缓存，可能不是最新）" if news.get("cached") else ""
                extra.append(f"{news['date']} 的新闻{tag}：{heads}")
    except Exception:
        pass
    try:
        city = detect_city(text)
        if city:
            line = switch_city(city)
            if line:
                extra.append(line)
        elif any(k in text for k in ("天气", "气温", "温度", "下雨", "几度", "多少度")):
            snap = city_snapshot()
            if snap:
                extra.append(
                    f"{snap['name']}当地此刻 {snap['local']}，{snap['desc']} {snap['temp']}°C。"
                )
        elif any(k in text for k in ("切换", "换到", "换成", "改成", "改为", "换城市", "换个城市")):
            extra.append("主人想换城市，但没能识别出城市名；请让主人直接说城市名，例如「切换到杭州」。")
    except Exception:
        pass
    return extra


def extract_facts(user_text: str, reply: str) -> list:
    prompt = (
        "从下面这轮对话里提炼关于主人、可能长期有用的事实（称呼、喜好、作息、正在做的事、状态）。"
        "只输出 JSON 数组，每项一句不超过 20 字；没有新事实就输出 []。\n"
        f"主人：{user_text}\n达妮卡：{reply}"
    )
    try:
        raw = ask_deepseek([{"role": "user", "content": prompt}], max_tokens=120, temperature=0.2)
        i, j = raw.find("["), raw.rfind("]")
        if i >= 0 and j > i:
            arr = json.loads(raw[i : j + 1])
            out = []
            for x in arr:
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict):
                    for k in ("fact", "text", "content", "内容", "item"):
                        if x.get(k):
                            out.append(str(x[k]))
                            break
            return [s[:30] for s in out if s][:5]
    except Exception:
        pass
    return []


class ChatWorker(QThread):
    done = Signal(str, str)  # (user_text, reply)

    def __init__(self, user_text: str):
        super().__init__()
        self.user_text = user_text

    def run(self) -> None:
        memory = load_memory()
        try:
            extra = chat_context_extra(self.user_text)
        except Exception:
            extra = []
        try:
            reply = ask_deepseek(build_messages(memory, self.user_text, extra))
        except Exception:
            self.done.emit(self.user_text, "")
            return
        if not reply:
            self.done.emit(self.user_text, "")
            return
        memory["history"] = (memory.get("history") or []) + [
            {"role": "user", "content": self.user_text},
            {"role": "assistant", "content": reply},
        ]
        memory["history"] = memory["history"][-20:]
        memory["count"] = int(memory.get("count") or 0) + 1
        facts = extract_facts(self.user_text, reply)
        if facts:
            cur = list(memory.get("facts") or [])
            for f in facts:
                if f and f not in cur:
                    cur.append(f)
            memory["facts"] = cur[-30:]
        save_memory(memory)
        append_conv_log(self.user_text, reply)
        self.done.emit(self.user_text, reply)



def today_tokens() -> tuple[int, int]:
    if not os.path.isdir(DSH_SESSIONS):
        return 0, 0
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    total = 0
    sessions = 0
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for root, _dirs, files in os.walk(DSH_SESSIONS):
        for name in files:
            if not name.endswith(".jsonl.zstd"):
                continue
            path = os.path.join(root, name)
            try:
                if ZSTD and os.path.exists(ZSTD):
                    out = subprocess.run(
                        [ZSTD, "-d", "-c", path],
                        capture_output=True,
                        timeout=60,
                        creationflags=flags,
                    ).stdout
                else:
                    out = open(path, "rb").read()
            except Exception:
                continue
            sessions += 1
            for line in out.splitlines():
                if b'"usage"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("type") != "assistant/message":
                    continue
                if (ev.get("time") or 0) < start:
                    continue
                u = (ev.get("data") or {}).get("usage") or {}
                total += int(u.get("totalTokens") or 0)
    return total, sessions


def fetch_balance() -> str:
    key = read_api_key()
    if not key:
        return "余额: 未取到 API Key"
    req = urllib.request.Request(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        infos = data.get("balance_infos") or []
        if not infos:
            return "余额: —"
        b = infos[0]
        return f"余额: {b.get('currency', '')} {b.get('total_balance', '—')}"
    except Exception as e:
        return f"余额: 获取失败({type(e).__name__})"


WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
WMO = {
    0: "晴", 1: "晴间多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 56: "冻雨", 57: "冻雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "阵雨", 82: "强阵雨", 85: "阵雪", 86: "阵雪",
    95: "雷阵雨", 96: "雷暴冰雹", 99: "雷暴冰雹",
}


def _get_json(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": "desktop-pet/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _locate() -> tuple[float, float, str]:
    # 每次现读 CONFIG：对话里切了城市，桌宠的天气气泡立刻跟着变
    return (
        float(CONFIG.get("lat") or CITY_LAT),
        float(CONFIG.get("lon") or CITY_LON),
        str(CONFIG.get("city") or CITY_NAME),
    )


def weather_line() -> str:
    now = datetime.now()
    date_str = f"{now.month}月{now.day}日 {WEEKDAYS[now.weekday()]}"
    city = str(CONFIG.get("city") or CITY_NAME)
    snap = city_snapshot()
    if snap:
        return f"{date_str}\n{snap['name']} {snap['desc']} {snap['temp']}°C"
    return f"{date_str}\n{city} 天气: 获取失败"


class WeatherWorker(QThread):
    done = Signal(str)

    def run(self) -> None:
        self.done.emit(weather_line())


class StatsWorker(QThread):
    done = Signal(str)

    def run(self) -> None:
        tokens, sessions = today_tokens()
        bal = fetch_balance()
        if tokens >= 1_000_000:
            t = f"{tokens / 1_000_000:.2f}M"
        elif tokens >= 1000:
            t = f"{tokens / 1000:.1f}K"
        else:
            t = str(tokens)
        self.done.emit(f"今日 tokens: {t}（{sessions} 个会话）\n{bal}")



class SpeechWindow(QWidget):
    """原神任务对白样式：黄色名字 + 金线 + 白字 + 黄色实心条，灰到浅的渐变底。"""

    MAXW = 300

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 rgba(56,60,68,232), stop:1 rgba(178,182,190,150));"
            "border-radius:8px; padding:9px 12px;"
        )
        self.label.setFont(QFont("Microsoft YaHei", 9))

    def show_text(self, text: str, anchor: QRect, side: bool = False):
        html = (
            '<div style="text-align:center;">'
            '<div style="color:#f3c53a; font-weight:700; font-size:10pt;">达妮卡</div>'
            '<div style="color:#c9a227; font-size:8pt; letter-spacing:2px;">◆──────────────────────◆</div>'
            f'<div style="color:#ffffff; font-size:9pt; margin-top:3px;">{text}</div>'
            '<div style="color:#f3c53a; font-size:7pt; margin-top:8px;">████████████</div>'
            "</div>"
        )
        self.label.setText(html)
        self.label.setFixedWidth(self.MAXW)
        self.label.adjustSize()
        self.resize(self.label.size())
        self._place(anchor, side)
        self.show()
        self.raise_()

    def _place(self, anchor: QRect, side: bool = False):
        """side=False：贴在人物头顶正上方；side=True：贴右侧，放不下就翻到左侧。"""
        scr = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        area = scr.availableGeometry()
        gap = 8

        if not side:
            x = anchor.center().x() - self.width() // 2
            y = anchor.top() - self.height() - gap
            if y < area.top() + 4:
                y = anchor.bottom() + gap
            x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
            self.move(x, y)
            return

        y = anchor.center().y() - self.height() // 2
        y = max(area.top() + 4, min(y, area.bottom() - self.height() - 4))

        x = anchor.right() + gap
        if x + self.width() > area.right() - 4:
            x = anchor.left() - self.width() - gap
        x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
        self.move(x, y)


class ChatInput(QDialog):
    """游戏内聊天气泡样式的输入框：深色圆角底 + 白色对话框图标 + 白字。"""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        icon = QLabel()
        icon.setFixedSize(30, 30)
        icon.setPixmap(self._bubble_icon(30))
        icon.setStyleSheet("background:transparent;")

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("和达妮卡说点什么…")
        self.edit.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.edit.setStyleSheet(
            "QLineEdit{background:transparent;border:none;color:#f4f7fa;padding:0;}"
            "QLineEdit::placeholder{color:#9aa6b2;}"
        )
        self.edit.returnPressed.connect(self.accept)

        closex = QPushButton("✕")
        closex.setFixedSize(22, 22)
        closex.setCursor(Qt.PointingHandCursor)
        closex.setStyleSheet(
            "QPushButton{background:transparent;color:#aab6c2;border:none;font-size:10pt;}"
            "QPushButton:hover{color:#ffffff;}"
        )
        closex.clicked.connect(self.reject)

        lay.addWidget(icon)
        lay.addWidget(self.edit, 1)
        lay.addWidget(closex)
        self.resize(450, 54)
        self._shown_at = 0.0

    def showEvent(self, ev):
        super().showEvent(ev)
        self._shown_at = time.time()
        self._accepted = False
        # 保证输入框拿到键盘焦点：否则用户打字没有反应
        QTimer.singleShot(0, self._grab_focus)

    def _grab_focus(self):
        self.raise_()
        self.activateWindow()
        self.edit.setFocus(Qt.OtherFocusReason)

    def accept(self):
        self._accepted = True
        super().accept()

    def reject(self):
        # 回车已经确认过就别再被「窗口失活」覆盖成取消
        if getattr(self, "_accepted", False):
            return
        super().reject()

    def event(self, ev):
        # 点到别处（窗口失去激活）就当作取消
        if ev.type() == QEvent.WindowDeactivate and not getattr(self, "_accepted", False):
            if time.time() - self._shown_at > 0.3:
                self.reject()
                return True
        return super().event(ev)

    @staticmethod
    def _bubble_icon(size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(0, 0, size, size)
        p.setBrush(QColor(43, 48, 53))
        r = max(2.0, size / 9.0)
        for dx in (-size * 0.24, 0, size * 0.24):
            p.drawEllipse(QPointF(size / 2 + dx, size / 2), r, r)
        p.end()
        return pm

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 20, 20)
        p.fillPath(path, QColor(43, 48, 53, 240))
        p.setPen(QPen(QColor(90, 100, 112, 140), 1))
        p.drawPath(path)

    def text(self) -> str:
        return self.edit.text().strip()


class MemoryDialog(QDialog):
    """「她记得的事」：深蓝半透明对话回顾面板，默认 5 轮，可展开到 20 轮。"""

    def __init__(self, parent, count: int, pairs: list):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.pairs = pairs
        self.expanded = False
        self.setMinimumSize(430, 360)
        self.resize(480, 430)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("对话回顾")
        title.setStyleSheet("color:#e8eef5; font-size:12pt; font-weight:600;")
        sub = QLabel(f"聊过 {count} 轮")
        sub.setStyleSheet("color:#8fa3b8; font-size:9pt; margin-left:8px;")
        closex = QPushButton("✕")
        closex.setFixedSize(26, 26)
        closex.setCursor(Qt.PointingHandCursor)
        closex.setStyleSheet(
            "QPushButton{background:transparent;color:#c9d4e0;border:none;font-size:11pt;}"
            "QPushButton:hover{color:#ffffff;}"
        )
        closex.clicked.connect(self.accept)
        header.addWidget(title)
        header.addWidget(sub)
        header.addStretch(1)
        header.addWidget(closex)
        root.addLayout(header)

        self.view = QTextBrowser()
        self.view.setFrameShape(QTextBrowser.NoFrame)
        self.view.setStyleSheet(
            "QTextBrowser{background:transparent;border:none;color:#dbe4ee;font-size:10pt;}"
        )
        root.addWidget(self.view, 1)

        btn_css = (
            "QPushButton{background:#243244;color:#dbe4ee;border:1px solid #33465c;"
            "border-radius:6px;padding:4px 12px;font-size:9pt;}"
            "QPushButton:hover{background:#2d3f55;}"
            "QPushButton:disabled{color:#6a7a8c;border-color:#2a394b;}"
        )
        row = QHBoxLayout()
        self.toggle_btn = QPushButton("展开")
        self.toggle_btn.setStyleSheet(btn_css)
        self.toggle_btn.clicked.connect(self.toggle)
        if len(pairs) <= 5:
            self.toggle_btn.setEnabled(False)
            self.toggle_btn.setToolTip("还没有更多记录")
        export_btn = QPushButton("导出全部记录")
        export_btn.setStyleSheet(btn_css)
        export_btn.clicked.connect(self.export_log)
        row.addWidget(self.toggle_btn)
        row.addWidget(export_btn)
        row.addStretch(1)
        root.addLayout(row)

        self.render()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        p.fillPath(path, QColor(19, 29, 41, 244))
        p.setPen(QPen(QColor(56, 78, 100, 180), 1))
        p.drawPath(path)

    def toggle(self):
        self.expanded = not self.expanded
        self.toggle_btn.setText("收起" if self.expanded else "展开")
        self.render()

    def render(self):
        n = 20 if self.expanded else 5
        chunk = self.pairs[-n:]
        if not chunk:
            self.view.setHtml('<div style="color:#8fa3b8;">还没聊过什么。</div>')
            return
        rows = []
        for u, a in chunk:
            rows.append(
                '<div style="margin-bottom:12px;">'
                '<div><span style="color:#e6c07b;font-weight:600;">主人</span>'
                f'<span style="color:#dbe4ee;">　{html.escape(str(u))}</span></div>'
                '<div style="margin-top:3px;"><span style="color:#9fc2ea;font-weight:600;">达妮卡</span>'
                f'<span style="color:#c9d6e2;">　{html.escape(str(a))}</span></div>'
                "</div>"
            )
        self.view.setHtml("".join(rows))

    def export_log(self):
        base = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or os.path.expanduser("~")
        default = os.path.join(base, f"达妮卡对话记录-{datetime.now():%Y%m%d}.txt")
        path, _ = QFileDialog.getSaveFileName(self, "导出全部对话记录", default, "文本文件 (*.txt)")
        if not path:
            return
        lines = []
        try:
            if os.path.exists(CONV_LOG_PATH):
                with open(CONV_LOG_PATH, encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            rec = json.loads(raw)
                        except Exception:
                            continue
                        t = str(rec.get("time", "")).replace("T", " ")[:16]
                        lines.append(f"[{t}] 主人：{rec.get('user', '')}")
                        lines.append(f"         达妮卡：{rec.get('reply', '')}")
                        lines.append("")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        if not lines:
            lines = ["（还没有对话记录。）"]
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("\n".join(lines))
            QMessageBox.information(self, "导出完成", f"已导出到：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))



KB_CROP = (320, 915)
KB_PASTE = (66, 930)
KB_SCALE = 2.0

KEY_ROWS = [
    ("1234567890", 968, 390, 45.5),
    ("QWERTYUIOP", 1002, 388, 45.5),
    ("ASDFGHJKL", 1036, 402, 45.5),
    ("ZXCVBNM", 1070, 408, 45.5),
]
KEYMAP = {}
for _row, _y, _x0, _pitch in KEY_ROWS:
    for _i, _ch in enumerate(_row):
        _bx = _x0 + _i * _pitch
        KEYMAP[_ch] = (
            int(KB_PASTE[0] + (_bx - KB_CROP[0]) * KB_SCALE),
            int(KB_PASTE[1] + (_y - KB_CROP[1]) * KB_SCALE),
            int(42 * KB_SCALE),
            int(30 * KB_SCALE),
        )
KEYMAP["SPACE"] = (
    int(KB_PASTE[0] + (545 - KB_CROP[0]) * KB_SCALE),
    int(KB_PASTE[1] + (1104 - KB_CROP[1]) * KB_SCALE),
    int(150 * KB_SCALE),
    int(22 * KB_SCALE),
)
MOUSE_CENTER = (150, 1030)
MOUSE_RADIUS = 46

# 若 assets/keymap.json 存在（键盘做过缩放/旋转），以它为准
try:
    with open(os.path.join(ASSETS, "keymap.json"), encoding="utf-8") as _f:
        _km = json.load(_f)
    _loaded = {k: tuple(v) for k, v in _km.items() if not k.startswith("_")}
    if _loaded:
        KEYMAP = _loaded
except Exception:
    pass


def vk_to_label(vk: int) -> str | None:
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if vk == 0x20:
        return "SPACE"
    return None


class InputHook(QObject):
    """全局低级键鼠钩子：只读虚拟键码，不记录任何输入内容。

    关键点：CallNextHookEx 必须按 64 位 LRESULT 返回，否则返回值被截断成 0，
    系统会认为事件已被吞掉 —— 表现为鼠标键盘失灵。
    """

    key = Signal(str)
    mouse = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._thread = None
        self._tid = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        try:
            if self._tid:
                ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT
        except Exception:
            pass

    def _run(self):
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            WH_KEYBOARD_LL, WH_MOUSE_LL = 13, 14
            WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
            WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x0201, 0x0204

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_void_p),
                ]

            LRESULT = ctypes.c_ssize_t
            HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

            user32.SetWindowsHookExW.restype = ctypes.c_void_p
            user32.SetWindowsHookExW.argtypes = [
                ctypes.c_int,
                HOOKPROC,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            user32.CallNextHookEx.restype = ctypes.c_ssize_t
            user32.CallNextHookEx.argtypes = [
                ctypes.c_void_p,
                ctypes.c_int,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
            user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

            def kbd_proc(n_code, w_param, l_param):
                try:
                    if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        label = vk_to_label(int(kb.vkCode))
                        if label:
                            self.key.emit(label)
                except Exception:
                    pass
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            def mouse_proc(n_code, w_param, l_param):
                try:
                    if n_code == 0 and w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                        self.mouse.emit("L" if w_param == WM_LBUTTONDOWN else "R")
                except Exception:
                    pass
                return user32.CallNextHookEx(None, n_code, w_param, l_param)

            self._kbd_proc = HOOKPROC(kbd_proc)
            self._mouse_proc = HOOKPROC(mouse_proc)
            self._tid = int(kernel32.GetCurrentThreadId())
            h1 = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kbd_proc, None, 0)
            h2 = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, None, 0)
            msg = wintypes.MSG()
            while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if h1:
                user32.UnhookWindowsHookEx(h1)
            if h2:
                user32.UnhookWindowsHookEx(h2)
        except Exception:
            pass


class Pet(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.idle = QPixmap(os.path.join(ASSETS, "idle.png"))
        self.angry = QPixmap(os.path.join(ASSETS, "angry.png"))
        self.egg = QPixmap(os.path.join(ASSETS, "egg.png"))
        self.typing = QPixmap(os.path.join(ASSETS, "typing.png"))
        self.mode = "idle"
        self.pix = self.idle
        self._ph = PET_HEIGHT
        self._scale = 1.0
        self._drag = None
        self._clicks = 0
        self._clicks_ts = 0.0
        self._want_stats = False
        self._want_weather = False
        self._daze = 0
        self._hidden_for_fullscreen = False
        self._fs_typing = bool(CONFIG.get("fs_typing", True))
        self._hwnd = 0
        self._started = time.time()
        self._rest_notice = 0
        self._bucket = time_bucket()
        self._secret_ready = False
        self._secret_clicks = 0
        self._secret_ts = 0.0
        self._pressed = {}
        self._mouse_hot_until = 0.0
        self._typing_until = 0.0

        self.speech = SpeechWindow()

        # 全局键鼠监听（只读虚拟键码，不记录内容）
        try:
            enabled = bool(CONFIG.get("input_hook", True)) and not os.environ.get("PET_NO_HOOK")
            self.hook = InputHook(self) if enabled else None
            if self.hook:
                self.hook.key.connect(self._on_key)
                self.hook.mouse.connect(self._on_mouse)
                self.hook.start()
        except Exception:
            self.hook = None

        self.timer_keys = QTimer(self)
        self.timer_keys.timeout.connect(self._tick_keys)
        self.timer_keys.start(80)

        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self.speech.hide)

        self.resize(*self._base_size())

        self.timer_fs = QTimer(self)
        self.timer_fs.timeout.connect(self.check_fullscreen)
        self.timer_fs.start(600)

        self.timer_bubble = QTimer(self)
        self.timer_bubble.timeout.connect(self._auto_bubble)
        self.timer_bubble.start(30_000)

        QTimer.singleShot(1500, self._greet)

        self.timer_weather = QTimer(self)
        if _WEATHER_ON:
            self.timer_weather.timeout.connect(self._auto_weather)
            self.timer_weather.start(30 * 60_000)
            QTimer.singleShot(7000, self._auto_weather)

        self.timer_clock = QTimer(self)
        self.timer_clock.timeout.connect(self._tick_clock)
        self.timer_clock.start(60_000)

        self._restore_pos()

    # ---- 几何 ----
    def _base_size(self):
        if self.pix.isNull():
            return 240, 300
        w = int(self.pix.width() * self._ph / self.pix.height())
        return w + 12, self._ph + 26

    scale = Property(
        float,
        lambda self: self._scale,
        lambda self, v: (setattr(self, "_scale", v), self.update()),
    )

    def paintEvent(self, _ev):
        if self.pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        s = self._scale
        w = int(self.pix.width() * self._ph / self.pix.height() * s)
        h = int(self._ph * s)
        x = (self.width() - w) // 2
        y = self.height() - h
        p.drawPixmap(x, y, w, h, self.pix)
        if self.pix is self.typing and not self.typing.isNull():
            self._paint_keys(p, x, y, w)

    def _paint_keys(self, p: QPainter, ox: int, oy: int, dw: int):
        if self.typing.width() <= 0:
            return
        sc = dw / float(self.typing.width())
        now = time.time()
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.2))
        for label, until in list(self._pressed.items()):
            if until < now:
                continue
            rect = KEYMAP.get(label)
            if not rect:
                continue
            kx, ky, kw, kh = rect
            r = QRectF(ox + kx * sc, oy + ky * sc, kw * sc, kh * sc)
            p.setBrush(QColor(0, 200, 255, 140))
            p.drawRoundedRect(r, 3, 3)
        if now < self._mouse_hot_until:
            cx, cy = MOUSE_CENTER
            rr = MOUSE_RADIUS * sc
            p.setBrush(QColor(0, 200, 255, 120))
            p.setPen(QPen(QColor(255, 255, 255, 180), 1.2))
            p.drawEllipse(QPointF(ox + cx * sc, oy + cy * sc), rr, rr)

    def _on_key(self, label: str):
        self._pressed[label] = time.time() + 0.16
        if self.mode in ("idle", "typing"):
            if self.mode != "typing":
                self.set_mode("typing")
            self._typing_until = time.time() + 0.7
            self._sync_visibility()
        self.update()

    def _on_mouse(self, _btn: str):
        # 用鼠标不切换画面，只让鼠标位置闪一下
        self._mouse_hot_until = time.time() + 0.18
        self.update()

    def _tick_keys(self):
        now = time.time()
        changed = False
        for label in list(self._pressed):
            if self._pressed[label] < now:
                del self._pressed[label]
                changed = True
        if self._mouse_hot_until and now > self._mouse_hot_until:
            self._mouse_hot_until = 0.0
            changed = True
        if (
            self.mode == "typing"
            and not self._pressed
            and self._typing_until
            and now > self._typing_until
        ):
            self.set_mode("idle")
            self._sync_visibility()
            changed = True
        if changed:
            self.update()

    def closeEvent(self, ev):
        if getattr(self, "hook", None):
            self.hook.stop()
        super().closeEvent(ev)

    def resizeEvent(self, _ev):
        pass

    def moveEvent(self, _ev):
        if self.speech.isVisible():
            self.speech._place(self.frameGeometry(), getattr(self, "_speech_side", False))

    # ---- 交互 ----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)
            ev.accept()

    def mouseReleaseEvent(self, ev):
        self._drag = None
        self._save_pos()

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        now = time.time()
        if now - self._clicks_ts > 8:
            self._clicks = 0
        self._clicks_ts = now
        self._clicks += 1

        # 隐藏彩蛋第二阶段：解谜成功后的十连击
        if getattr(self, "_secret_ready", False):
            if now - getattr(self, "_secret_ts", 0) > 12:
                self._secret_clicks = 0
                self._secret_ts = now
            self._secret_clicks = getattr(self, "_secret_clicks", 0) + 1
            if self._secret_clicks >= 10:
                self._secret_ready = False
                self._secret_clicks = 0
                self._clicks = 0
                self.set_mode("egg")
                self.bounce()
                self.say("……好吧，被您找到了。秘密是：我也会累。", 8000)
                QTimer.singleShot(8000, lambda: self.set_mode("idle"))
                return
        elif now - getattr(self, "_secret_ts", 0) > 12 and self._clicks > 1:
            self._secret_clicks = 0

        if self._clicks >= 5:
            self._clicks = 0
            self._want_stats = False
            self._want_weather = False
            self._daze = 0
            self.bounce()
            self.set_mode("angry")
            self.say("够了，主人。", 5000)
            QTimer.singleShot(5_000, lambda: self.set_mode("idle"))
            return

        # 走神彩蛋：连续两次无反应，第三次必定冒一句
        if self._daze >= 2:
            self._daze = 0
            self.set_mode("egg")
            self.bounce()
            self.say(DAZE_LINE, 5000)
            QTimer.singleShot(5000, lambda: self.set_mode("idle"))
            return
        if random.random() < DAZE_CHANCE:
            self._daze += 1
            return
        self._daze = 0
        self.bounce()

        pick = random.random()
        if pick < CHAT_CHANCE:
            self._want_stats = False
            self._want_weather = False
            self.say(random.choice(BUBBLES))
        elif pick < CHAT_CHANCE + STATS_CHANCE:
            self._want_weather = False
            self._want_stats = True
            self.say("今日 tokens: 统计中…", 5000)
            self.refresh_stats()
        else:
            self._want_stats = False
            self._want_weather = True
            self.say("天气: 获取中…", 5000)
            self.refresh_weather()

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        act_chat = QAction("和她说句话（联网）", self)
        act_chat.triggered.connect(lambda *_: self.menu_chat())
        act_mem = QAction("她记得什么", self)
        act_mem.triggered.connect(lambda *_: self.menu_memory())
        act_refresh = QAction("刷新 token / 余额", self)
        act_refresh.triggered.connect(lambda *_: self.menu_stats())
        act_weather = QAction("看日期 / 天气", self)
        act_weather.triggered.connect(lambda *_: self.menu_weather())
        act_idle = QAction("换回常态", self)
        act_idle.triggered.connect(lambda *_: self.menu_idle())
        act_link = QAction("重建桌面快捷方式", self)
        act_link.triggered.connect(lambda *_: self.menu_shortcut())
        self.act_hook = QAction("暂停键鼠监听", self)
        self.act_hook.triggered.connect(lambda *_: self.toggle_hook())
        self.act_fs = QAction("全屏时显示打字动画", self)
        self.act_fs.setCheckable(True)
        self.act_fs.setChecked(self._fs_typing)
        self.act_fs.triggered.connect(lambda *_: self.toggle_fs_typing())
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(lambda *_: QApplication.instance().quit())
        menu.addAction(act_chat)
        menu.addAction(act_mem)
        menu.addSeparator()
        menu.addAction(act_refresh)
        menu.addAction(act_weather)
        menu.addAction(act_idle)
        menu.addAction(act_link)
        menu.addAction(self.act_hook)
        menu.addAction(self.act_fs)
        menu.addSeparator()
        menu.addAction(act_quit)
        menu.exec(ev.globalPos())

    def toggle_hook(self):
        if not getattr(self, "hook", None):
            self.say("键鼠监听没有启动。", 4000)
            return
        if getattr(self.hook, "_running", False):
            self.hook.stop()
            self.act_hook.setText("恢复键鼠监听")
            self.say("键鼠监听已暂停。", 4000)
        else:
            self.hook.start()
            self.act_hook.setText("暂停键鼠监听")
            self.say("键鼠监听已恢复。", 4000)

    def menu_stats(self):
        self._want_stats = True
        self.say("今日 tokens: 统计中…", 5000)
        self.refresh_stats()

    def menu_weather(self):
        self._want_weather = True
        self.say("天气: 获取中…", 5000)
        self.refresh_weather(True)

    def menu_idle(self):
        was_angry = self.mode == "angry"
        self.set_mode("idle")
        self.say("好了，主人。" if was_angry else "本来就是常态，主人。", 4000)

    def _side_pos(self, w: int, h: int):
        """把宽 w 高 h 的窗口摆到人物右侧；右侧放不下就翻到左侧。"""
        anchor = self.frameGeometry()
        scr = QApplication.screenAt(anchor.center()) or QApplication.primaryScreen()
        area = scr.availableGeometry()
        gap = 8
        x = anchor.right() + gap
        if x + w > area.right() - 4:
            x = anchor.left() - w - gap
        x = max(area.left() + 4, min(x, area.right() - w - 4))
        y = anchor.center().y() - h // 2
        y = max(area.top() + 4, min(y, area.bottom() - h - 4))
        return x, y

    def menu_chat(self):
        dlg = ChatInput(self)
        x, y = self._side_pos(dlg.width(), dlg.height())
        dlg.move(x, y)
        if dlg.exec():
            text = dlg.text()
            if not text:
                return
            if text.replace(" ", "") in ("触发彩蛋", "触发彩蛋！", "触发彩蛋!"):
                self.trigger_egg()
                return
            self.chat(text)

    def trigger_egg(self):
        """隐藏彩蛋：输入暗号后只冒一句，配害羞脸。"""
        self._last_chat_ts = time.time()
        self.set_mode("egg")
        self.bounce()
        self.say("才不是在想薇斯纳呢", 6000)
        QTimer.singleShot(6000, lambda: self.set_mode("idle"))

    def _arm_secret(self):
        self._secret_ready = True
        self._secret_clicks = 0
        self._secret_ts = time.time()

    def chat(self, text: str):
        self._last_chat_ts = time.time()
        self.say("嗯…让我想想。", 4000)
        self._chat_worker = ChatWorker(text)
        self._chat_worker.done.connect(self._on_chat)
        self._chat_worker.start()

    def _chat_quiet(self) -> bool:
        """对话刚结束的一段时间内，不让随机气泡/天气抢先覆盖她的回答。"""
        return time.time() - getattr(self, "_last_chat_ts", 0.0) > 20

    def _auto_bubble(self):
        if self._chat_quiet():
            self.say(random.choice(BUBBLES))

    def _auto_weather(self):
        if self._chat_quiet():
            self.refresh_weather(True)

    def _greet(self):
        self._bucket = time_bucket()
        if CONFIG.get("time_lines", True):
            self.say(random.choice(TIME_LINES[self._bucket]), 6000)
        else:
            self.say("主人，我在这儿。双击我试试。")

    def _tick_clock(self):
        # 时段切换：换一条应景的话
        b = time_bucket()
        if b != self._bucket:
            self._bucket = b
            if CONFIG.get("time_lines", True) and self._chat_quiet():
                self.say(random.choice(TIME_LINES[b]), 7000)
        # 久坐提醒
        try:
            interval = int(CONFIG.get("rest_reminder_minutes") or 0)
        except Exception:
            interval = 0
        if interval <= 0:
            return
        minutes = (time.time() - self._started) / 60.0
        due = int(minutes // interval)
        if due > self._rest_notice and self._chat_quiet():
            self._rest_notice = due
            total = due * interval
            span = f"{total} 分钟" if total < 60 else f"{total // 60} 小时"
            self.say(f"主人，我已经陪您坐了 {span}。起来走动一下吧。", 8000)

    def _on_chat(self, _user_text: str, reply: str):
        if self._hidden_for_fullscreen:
            return
        if not reply:
            self.say("主人，云端没连上。检查一下 API Key。", 6000)
            return
        self._last_chat_ts = time.time()
        self.say(reply, 12000)

    def menu_memory(self):
        m = load_memory()
        hist = m.get("history") or []
        pairs = []
        i = 0
        while i < len(hist):
            item = hist[i] if isinstance(hist[i], dict) else {}
            if item.get("role") == "user":
                nxt = hist[i + 1] if i + 1 < len(hist) and isinstance(hist[i + 1], dict) else {}
                pairs.append((item.get("content", ""), nxt.get("content", "")))
                i += 2
            else:
                i += 1

        dlg = MemoryDialog(self, int(m.get("count") or 0), pairs)
        x, y = self._side_pos(dlg.width(), dlg.height())
        dlg.move(x, y)
        dlg.exec()

    def menu_shortcut(self):
        ensure_desktop_shortcut(force=True)
        self.say("桌面快捷方式已更新。", 4000)

    def refresh_weather(self, force: bool = True):
        self._want_weather = force or self._want_weather
        self._weather_worker = WeatherWorker(self)
        self._weather_worker.done.connect(self._on_weather)
        self._weather_worker.start()

    def _on_weather(self, text: str):
        if self._want_weather:
            self._want_weather = False
            self.say(text, 6000)

    def set_mode(self, mode: str):
        old_h = self.height()
        self.mode = mode
        if mode == "angry":
            self.pix = self.angry
        elif mode == "egg":
            self.pix = self.egg
        elif mode == "typing":
            self.pix = self.typing
        else:
            self.pix = self.idle
        self._ph = TYPING_HEIGHT if mode == "typing" else PET_HEIGHT
        self.resize(*self._base_size())
        # 窗口高度变了就按「底边不动」补偿，否则人物会被顶到屏幕外
        new_h = self.height()
        if old_h and new_h != old_h:
            self.move(self.x(), self.y() - (new_h - old_h))
        self._clamp_on_screen()
        self.update()

    def _clamp_on_screen(self):
        scr = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        if not scr:
            return
        a = scr.availableGeometry()
        x = max(a.left() + 4, min(self.x(), a.right() - self.width() - 4))
        y = max(a.top() + 4, min(self.y(), a.bottom() - self.height() - 4))
        if x != self.x() or y != self.y():
            self.move(x, y)

    def bounce(self):
        anim = QPropertyAnimation(self, b"scale", self)
        anim.setDuration(360)
        anim.setKeyValueAt(0.0, 1.0)
        anim.setKeyValueAt(0.35, 1.18)
        anim.setKeyValueAt(0.65, 0.92)
        anim.setKeyValueAt(1.0, 1.0)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.start(QPropertyAnimation.DeleteWhenStopped)
        self._bounce_anim = anim

    def say(self, text: str, ms: int = 5000, side: bool = False):
        if self._hidden_for_fullscreen:
            return
        self._speech_side = side
        self.speech.show_text(text, self.frameGeometry(), side)
        self._bubble_timer.start(ms)

    # ---- 数据 ----
    def refresh_stats(self, force: bool = False):
        self._want_stats = self._want_stats or force
        self._worker = StatsWorker(self)
        self._worker.done.connect(self._on_stats)
        self._worker.start()

    def _on_stats(self, text: str):
        if self._want_stats:
            self._want_stats = False
            self.say(text, 5000)

    # ---- 全屏检测 ----
    def check_fullscreen(self):
        if not self._hwnd:
            self._hwnd = int(self.winId())
        fs = foreground_is_fullscreen(self._hwnd)
        if fs and not self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = True
            self._bubble_timer.stop()
            self.timer_bubble.stop()
            self.timer_weather.stop()
            self.speech.hide()
            self._sync_visibility()
        elif not fs and self._hidden_for_fullscreen:
            self._hidden_for_fullscreen = False
            self._sync_visibility()
            self.raise_()
            self.timer_bubble.start(30_000)
            if _WEATHER_ON:
                self.timer_weather.start(30 * 60_000)
        if os.environ.get("PET_DEBUG") and fs != getattr(self, "_last_fs", None):
            self._last_fs = fs
            print(f"FULLSCREEN {fs} at {time.strftime('%H:%M:%S')}", flush=True)

    def _sync_visibility(self):
        """全屏时默认隐藏；若开了「全屏打字动画」且正在打字，则临时浮到前台。"""
        popup = self._hidden_for_fullscreen and self._fs_typing and self.mode == "typing"
        if popup:
            if not self.isVisible():
                self.show()
            self.raise_()
        elif self._hidden_for_fullscreen:
            if self.isVisible():
                self.hide()
        else:
            if not self.isVisible():
                self.show()

    def toggle_fs_typing(self):
        self._fs_typing = not self._fs_typing
        CONFIG["fs_typing"] = self._fs_typing
        save_config()
        if hasattr(self, "act_fs"):
            self.act_fs.setChecked(self._fs_typing)
        self._sync_visibility()
        if not self._hidden_for_fullscreen:
            self.say("全屏打字动画已" + ("开启" if self._fs_typing else "关闭") + "。", 4000)

    def _state_path(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
        except Exception:
            pass
        return os.path.join(STATE_DIR, "pos.json")

    def _save_pos(self):
        try:
            json.dump({"x": self.x(), "y": self.y()}, open(self._state_path(), "w"))
        except Exception:
            pass

    def _restore_pos(self):
        try:
            d = json.load(open(self._state_path()))
            self.move(int(d["x"]), int(d["y"]))
            return
        except Exception:
            pass
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.right() - self.width() - 40, scr.bottom() - self.height() - 40)


def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def ensure_desktop_shortcut(force: bool = False) -> None:
    """在桌面放一个带图标的启动快捷方式：打包版指向 exe，源码版指向 pythonw + app.py。"""
    try:
        desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
        if not desktop or not os.path.isdir(desktop):
            return
        lnk = os.path.join(desktop, "达妮卡桌宠.lnk")
        if os.path.exists(lnk) and not force:
            return
        if FROZEN:
            exe = sys.executable
            args = ""
            icon = exe + ",0"
        else:
            # 源码运行：用同目录的 pythonw.exe 拉起 app.py
            py = sys.executable
            pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
            exe = pyw if os.path.exists(pyw) else py
            args = '"' + os.path.join(APP_DIR, "app.py") + '"'
            ico = os.path.join(APP_DIR, "icon.ico")
            icon = (ico + ",0") if os.path.exists(ico) else (exe + ",0")
        script = (
            "$ws = New-Object -ComObject WScript.Shell;"
            f"$sc = $ws.CreateShortcut({_ps_quote(lnk)});"
            f"$sc.TargetPath = {_ps_quote(exe)};"
            f"$sc.Arguments = {_ps_quote(args)};"
            f"$sc.WorkingDirectory = {_ps_quote(APP_DIR)};"
            f"$sc.IconLocation = {_ps_quote(icon)};"
            "$sc.Description = '达妮卡桌宠';"
            "$sc.Save()"
        )
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def main() -> int:
    app = QApplication(sys.argv)
    # 桌宠是 Qt.Tool 窗口，不计入「最后窗口」；开着它会让关闭对话框时误退出进程
    app.setQuitOnLastWindowClosed(False)

    # 供「安装快捷方式.cmd」调用：只建快捷方式、不启动桌宠
    if "--install-shortcut" in sys.argv:
        ensure_desktop_shortcut(force=True)
        QMessageBox.information(None, "达妮卡桌宠", "桌面快捷方式已创建。")
        return 0

    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    probe = QLocalSocket()
    probe.connectToServer("desktop-pet-danica")
    if probe.waitForConnected(300):
        probe.disconnectFromServer()
        print("ALREADY_RUNNING")
        return 0
    server = QLocalServer()
    QLocalServer.removeServer("desktop-pet-danica")
    server.listen("desktop-pet-danica")

    pet = Pet()
    pet.show()
    ensure_desktop_shortcut()

    if os.environ.get("PET_DEBUG"):
        print(f"PET_STARTED pid={os.getpid()} geom={pet.geometry().getRect()} size={pet.size().toTuple()}", flush=True)
        hb = QTimer()
        hb.timeout.connect(lambda: print(f"PET_TICK {time.strftime('%H:%M:%S')} vis={pet.isVisible()}", flush=True))
        hb.start(5000)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

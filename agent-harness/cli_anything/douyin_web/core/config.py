from pathlib import Path
import os


DOUYIN_HOME_ENV = "DOUYIN_WEB_HOME"
BROWSER_PATH_ENV = "DOUYIN_BROWSER_PATH"

DEFAULT_HOME = Path("~/.douyin-web-cli").expanduser()
DEFAULT_USER_DATA_DIR_NAME = "browser-profile"
DEFAULT_PORT = 9223

ROOT_URL = "https://www.douyin.com/"

FEED_URLS = {
    "home": ROOT_URL,
    "recommend": "https://www.douyin.com/?recommend=1",
    "jingxuan": "https://www.douyin.com/jingxuan",
    "featured": "https://www.douyin.com/jingxuan",
    "search": "https://www.douyin.com/aisearch",
    "ai-search": "https://www.douyin.com/aisearch",
    "follow": "https://www.douyin.com/follow",
    "following": "https://www.douyin.com/follow",
    "friend": "https://www.douyin.com/friend",
    "friends": "https://www.douyin.com/friend",
    "mine": "https://www.douyin.com/user/self",
    "me": "https://www.douyin.com/user/self",
    "live": "https://www.douyin.com/live",
    "vs": "https://www.douyin.com/vs",
    "cinema": "https://www.douyin.com/vs",
    "series": "https://www.douyin.com/series",
    "short-drama": "https://www.douyin.com/series",
    "upload": "https://creator.douyin.com/creator-micro/content/upload",
    "creator-manage": "https://creator.douyin.com/creator-micro/content/manage",
    "creator-data": "https://creator.douyin.com/creator-micro/data/stats/overview",
}

LOGIN_ACCOUNT_MARKERS = [
    "退出登录",
    "我的主页",
    "我的抖音",
]

LOGIN_BUTTON_MARKERS = [
    "登录",
    "手机号登录",
    "扫码登录",
]

LOGIN_COOKIE_MARKERS = [
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "uid_tt",
    "uid_tt_ss",
]

ACTION_TEXTS = {
    "clean": ["清屏"],
    "danmaku": ["弹幕", "关闭弹幕", "开启弹幕"],
    "fullscreen": ["全屏", "进入全屏"],
    "like": ["点赞", "喜欢"],
    "favorite": ["收藏"],
    "share": ["分享"],
    "comment": ["评论"],
    "sound": ["打开声音", "开启声音", "取消静音"],
}


def home_dir(path=None) -> Path:
    raw = path or os.environ.get(DOUYIN_HOME_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_HOME


def session_path(path=None) -> Path:
    return home_dir(path) / "session.json"


def history_path(path=None) -> Path:
    return home_dir(path) / "history.jsonl"


def default_user_data_dir(path=None) -> Path:
    return home_dir(path) / DEFAULT_USER_DATA_DIR_NAME


def feed_url(feed_or_url: str) -> str:
    value = feed_or_url.strip()
    if value.startswith("http://") or value.startswith("https://"):
        return value
    try:
        return FEED_URLS[value]
    except KeyError as exc:
        known = ", ".join(sorted(FEED_URLS))
        raise ValueError(f"unknown feed '{value}', expected one of: {known}") from exc

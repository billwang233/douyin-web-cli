from __future__ import annotations

from pathlib import Path
from typing import Optional
import asyncio
import time

from .config import default_user_data_dir, feed_url
from .state import ActionResult, SessionState, clear_session, load_session, save_session
from ..utils.browser_backend import (
    BrowserBackendError,
    DouyinPage,
    endpoint_ready,
    launch_remote_browser,
    pid_exists,
    terminate_browser,
)


def run_async(coro):
    return asyncio.run(coro)


def launch(
    url: str,
    home: Optional[str] = None,
    port: Optional[int] = None,
    browser_path: Optional[str] = None,
    user_data_dir: Optional[str] = None,
) -> ActionResult:
    profile_dir = Path(user_data_dir).expanduser() if user_data_dir else default_user_data_dir(home)
    try:
        launched = launch_remote_browser(
            url=url,
            user_data_dir=profile_dir,
            port=port,
            browser_path=browser_path,
        )
        state = SessionState(
            endpoint=launched["endpoint"],
            port=launched["port"],
            pid=launched["pid"],
            browser_path=launched["browser_path"],
            user_data_dir=launched["user_data_dir"],
            active_url=url,
        )
        save_session(state, home)
        return ActionResult(
            ok=True,
            action="launch",
            message="browser session ready",
            data={**state.to_dict(), "reused": launched["reused"]},
        )
    except Exception as exc:
        return ActionResult(False, "launch", str(exc))


def close(home: Optional[str] = None) -> ActionResult:
    state = load_session(home)
    terminated = terminate_browser(state.pid)
    clear_session(home)
    return ActionResult(
        ok=True,
        action="close",
        message="session cleared",
        data={"terminated_pid": state.pid if terminated else None},
    )


def state(home: Optional[str] = None) -> ActionResult:
    current = load_session(home)
    data = current.to_dict()
    data["endpoint_ready"] = endpoint_ready(current.endpoint) if current.endpoint else False
    data["pid_running"] = pid_exists(current.pid)
    return ActionResult(True, "state", "loaded session state", data=data)


def open_feed(feed: str, home: Optional[str] = None, auto_launch: bool = True) -> ActionResult:
    url = feed_url(feed)
    current = load_session(home)
    if not current.has_endpoint or not endpoint_ready(current.endpoint):
        if not auto_launch:
            return ActionResult(False, "open", "no active browser session; run `douyin-web launch` first")
        launched = launch(url=url, home=home)
        if not launched.ok:
            return launched
        current = load_session(home)
    try:
        data = run_async(_open_feed(current.endpoint, url))
        current.active_url = data.get("url", url)
        save_session(current, home)
        return ActionResult(True, "open", f"opened {feed}", data=data)
    except Exception as exc:
        return ActionResult(False, "open", str(exc), data={"url": url})


async def _open_feed(endpoint: str, url: str) -> dict:
    async with DouyinPage(endpoint) as page:
        return await page.goto(url)


def current(home: Optional[str] = None) -> ActionResult:
    return _with_page("current", home, lambda page: page.current())


def info(home: Optional[str] = None) -> ActionResult:
    return _with_page("info", home, lambda page: page.video_info())


def focus(home: Optional[str] = None) -> ActionResult:
    return _with_page("focus", home, lambda page: page.focus_window())


def reload_page(home: Optional[str] = None) -> ActionResult:
    return _with_page("reload", home, lambda page: page.reload())


def search(query: str, submit: bool = True, home: Optional[str] = None) -> ActionResult:
    return _with_page("search", home, lambda page: page.search(query=query, submit=submit))


def login_status(home: Optional[str] = None) -> ActionResult:
    current = load_session(home)
    if not current.has_endpoint or not endpoint_ready(current.endpoint):
        return ActionResult(False, "status", "no active browser session; run `douyin-web launch` first")
    try:
        data = run_async(_login_status(current.endpoint))
        return ActionResult(True, "status", f"login status: {data['status']}", data=data)
    except Exception as exc:
        return ActionResult(False, "status", str(exc))


async def _login_status(endpoint: str) -> dict:
    async with DouyinPage(endpoint) as page:
        return await page.login_status()


def wait_login(timeout_seconds: int, home: Optional[str] = None) -> ActionResult:
    current = load_session(home)
    if not current.has_endpoint or not endpoint_ready(current.endpoint):
        return ActionResult(False, "wait-login", "no active browser session; run `douyin-web launch` first")
    try:
        start = time.time()
        data = run_async(_wait_login(current.endpoint, timeout_seconds))
        elapsed = round(time.time() - start, 2)
        ok = data.get("status") == "logged_in"
        return ActionResult(
            ok=ok,
            action="wait-login",
            message="login detected" if ok else "login was not detected before timeout",
            data={**data, "elapsed_seconds": elapsed},
        )
    except Exception as exc:
        return ActionResult(False, "wait-login", str(exc))


async def _wait_login(endpoint: str, timeout_seconds: int) -> dict:
    async with DouyinPage(endpoint) as page:
        return await page.wait_login(timeout_seconds)


def player_action(action: str, home: Optional[str] = None) -> ActionResult:
    return _with_page(action, home, lambda page: page.set_playback(action))


def sound_action(mode: str, home: Optional[str] = None) -> ActionResult:
    return _with_page("sound", home, lambda page: page.sound(mode))


def seek(seconds: Optional[float] = None, percent: Optional[float] = None, home: Optional[str] = None) -> ActionResult:
    return _with_page("seek", home, lambda page: page.seek_video(seconds=seconds, percent=percent))


def rate(value: float, home: Optional[str] = None) -> ActionResult:
    return _with_page("rate", home, lambda page: page.set_rate(value))


def volume(value: float, home: Optional[str] = None) -> ActionResult:
    return _with_page("volume", home, lambda page: page.set_volume(value))


def navigate_video(direction: str, home: Optional[str] = None) -> ActionResult:
    return _with_page(direction, home, lambda page: page.navigate_video(direction))


def prepare(home: Optional[str] = None) -> ActionResult:
    return _with_page("prepare", home, lambda page: page.prepare_playback())


def dismiss(home: Optional[str] = None) -> ActionResult:
    return _with_page("dismiss", home, lambda page: page.dismiss_prompts())


def click_text(text: str, home: Optional[str] = None) -> ActionResult:
    return _with_page("click-text", home, lambda page: page.click_visible_text(text))


def press(key: str, home: Optional[str] = None) -> ActionResult:
    return _with_page("press", home, lambda page: page.press(key))


def comments(mode: str, home: Optional[str] = None) -> ActionResult:
    return _with_page("comments", home, lambda page: page.comments(mode))


def danmaku_send(text: str, submit: bool = False, home: Optional[str] = None) -> ActionResult:
    return _with_page("danmaku-send", home, lambda page: page.send_danmaku(text=text, submit=submit))


def text_action(action: str, home: Optional[str] = None, **kwargs) -> ActionResult:
    async def invoke(page: DouyinPage):
        if action == "fullscreen":
            return await page.fullscreen()
        if action == "clean":
            return await page.clean_screen()
        if action == "danmaku":
            return await page.danmaku(kwargs.get("mode", "toggle"))
        if action == "loop":
            return await page.toggle_loop()
        if action in {"like", "favorite", "share"}:
            return await page.click_action(action)
        raise BrowserBackendError(f"unsupported text action: {action}")

    return _with_page(action, home, invoke)


def follow_author(home: Optional[str] = None) -> ActionResult:
    return _with_page("follow-author", home, lambda page: page.follow_author())


def comment(text: str, submit: bool = False, home: Optional[str] = None) -> ActionResult:
    return _with_page("comment", home, lambda page: page.comment(text=text, submit=submit))


def screenshot(output: Path, home: Optional[str] = None) -> ActionResult:
    return _with_page("screenshot", home, lambda page: page.screenshot(output))


def _with_page(action: str, home: Optional[str], fn) -> ActionResult:
    current = load_session(home)
    if not current.has_endpoint or not endpoint_ready(current.endpoint):
        return ActionResult(False, action, "no active browser session; run `douyin-web launch` first")
    try:
        data = run_async(_invoke(current.endpoint, fn))
        return ActionResult(True, action, f"{action} completed", data=data)
    except Exception as exc:
        return ActionResult(False, action, str(exc))


async def _invoke(endpoint: str, fn) -> dict:
    async with DouyinPage(endpoint) as page:
        return await fn(page)

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional
import contextlib
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from ..core.config import ACTION_TEXTS, BROWSER_PATH_ENV, DEFAULT_PORT, LOGIN_COOKIE_MARKERS


class BrowserBackendError(RuntimeError):
    pass


RIGHT_RAIL_ACTION_SLOTS = {
    "like": 0,
    "comment": 1,
    "favorite": 2,
    "share": 3,
}


def find_free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in [preferred, 0]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                return int(sock.getsockname()[1])
        except OSError:
            continue
    raise BrowserBackendError("could not allocate a local port")


def endpoint_for_port(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def endpoint_ready(endpoint: str, timeout: float = 1.0) -> bool:
    try:
        _read_json(f"{endpoint.rstrip('/')}/json/version", timeout=timeout)
        return True
    except BrowserBackendError:
        return False


def wait_for_endpoint(endpoint: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if endpoint_ready(endpoint, timeout=0.5):
            return
        time.sleep(0.2)
    raise BrowserBackendError(f"browser endpoint did not become ready: {endpoint}")


def find_browser(explicit: Optional[str] = None) -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get(BROWSER_PATH_ENV)
    if env_path:
        candidates.append(env_path)
    candidates.extend(
        [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "google-chrome",
            "chromium",
            "chromium-browser",
            "msedge",
        ]
    )
    for candidate in candidates:
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
        else:
            resolved = _which(candidate)
            if resolved:
                return resolved
    raise BrowserBackendError(
        "could not find Chrome/Chromium. Set DOUYIN_BROWSER_PATH to a browser executable."
    )


def launch_remote_browser(
    url: str,
    user_data_dir: Path,
    port: Optional[int] = None,
    browser_path: Optional[str] = None,
    wait: bool = True,
) -> dict[str, Any]:
    chosen_port = port or find_free_port()
    endpoint = endpoint_for_port(chosen_port)
    if endpoint_ready(endpoint, timeout=0.5):
        return {
            "endpoint": endpoint,
            "port": chosen_port,
            "pid": None,
            "browser_path": browser_path,
            "user_data_dir": str(user_data_dir),
            "reused": True,
        }

    executable = find_browser(browser_path)
    user_data_dir.mkdir(parents=True, exist_ok=True)
    args = [
        executable,
        f"--remote-debugging-port={chosen_port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        url,
    ]
    proc = subprocess.Popen(  # noqa: S603
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    if wait:
        wait_for_endpoint(endpoint)
    return {
        "endpoint": endpoint,
        "port": chosen_port,
        "pid": proc.pid,
        "browser_path": executable,
        "user_data_dir": str(user_data_dir),
        "reused": False,
    }


def terminate_browser(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False


def pid_exists(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class DouyinPage:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._timeout_error = Exception

    async def __aenter__(self) -> "DouyinPage":
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise BrowserBackendError(
                "playwright is not installed. Run `python3 -m pip install -e agent-harness`."
            ) from exc

        self._timeout_error = PlaywrightTimeoutError
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.connect_over_cdp(self.endpoint)
        self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
        self.page = await self._pick_page()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._playwright:
            await self._playwright.stop()

    async def _pick_page(self):
        pages = list(self.context.pages)
        for page in pages:
            if "douyin.com" in page.url:
                await page.bring_to_front()
                return page
        if pages:
            await pages[0].bring_to_front()
            return pages[0]
        return await self.context.new_page()

    async def goto(self, url: str) -> dict[str, Any]:
        await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await self.page.bring_to_front()
        await self.page.wait_for_timeout(800)
        return {"url": self.page.url, "title": await self.page.title()}

    async def search(self, query: str, submit: bool = True) -> dict[str, Any]:
        for selector in ["input[placeholder*='搜索']", "input"]:
            locator = self.page.locator(selector)
            try:
                count = min(await locator.count(), 6)
                for index in range(count):
                    item = locator.nth(index)
                    if await _is_visible(item):
                        await item.click(timeout=2000)
                        await item.fill("")
                        await item.type(query, delay=15)
                        if submit:
                            await self.page.keyboard.press("Enter")
                            await self.page.wait_for_timeout(1200)
                        return {"query": query, "submitted": submit, "method": "search-input", "url": self.page.url}
            except Exception:
                pass
        if submit:
            url = f"https://www.douyin.com/search/{urllib.parse.quote(query)}"
            return {"query": query, "submitted": True, "method": "direct-url", **await self.goto(url)}
        raise BrowserBackendError("could not find the search input")

    async def _ensure_video_picker(self) -> None:
        await self.page.evaluate(VIDEO_PICKER_SCRIPT)

    async def current(self) -> dict[str, Any]:
        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "login": await self.login_status(),
            "video": await self.video_state(),
        }

    async def video_info(self) -> dict[str, Any]:
        await self._ensure_video_picker()
        return await self.page.evaluate(
            """
            () => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 4
                  && rect.height > 4
                  && rect.x < window.innerWidth
                  && rect.y < window.innerHeight
                  && rect.right > 0
                  && rect.bottom > 0
                  && style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity) > 0;
              };
              const textOf = (el) => (el?.innerText || el?.textContent || '').trim().replace(/\\s+/g, ' ');
              const video = pickDouyinVideo();
              const links = Array.from(document.querySelectorAll('a')).filter(visible).map((el) => ({
                text: textOf(el),
                href: el.href,
              }));
              const author = links.find((item) => item.text.startsWith('@')) || null;
              const hashtags = Array.from(new Set(links.filter((item) => item.text.startsWith('#')).map((item) => item.text))).slice(0, 20);
              const collection = Array.from(document.querySelectorAll('div,span,a')).filter(visible)
                .map((el) => textOf(el))
                .find((text) => text.includes('合集') || text.includes('下一集') || text.includes('下一章')) || null;
              return {
                url: location.href,
                title: document.title,
                author,
                hashtags,
                collection,
                video: video ? {
                  exists: true,
                  paused: video.paused,
                  muted: video.muted,
                  volume: video.volume,
                  playbackRate: video.playbackRate,
                  currentTime: video.currentTime,
                  duration: Number.isFinite(video.duration) ? video.duration : null,
                  width: video.videoWidth,
                  height: video.videoHeight,
                } : { exists: false },
                visibleTextSample: textOf(document.body).split(' ').filter(Boolean).slice(0, 80).join(' '),
              };
            }
            """
        )

    async def focus_window(self) -> dict[str, Any]:
        await self.page.bring_to_front()
        activation = activate_browser_app()
        await self.page.wait_for_timeout(500)
        return {
            "url": self.page.url,
            "title": await self.page.title(),
            "activation": activation,
        }

    async def reload(self) -> dict[str, Any]:
        await self.page.reload(wait_until="domcontentloaded", timeout=45000)
        await self.page.wait_for_timeout(800)
        return {"url": self.page.url, "title": await self.page.title()}

    async def click_text(self, candidates: Iterable[str], timeout: int = 1800) -> str:
        errors = []
        for text in candidates:
            locators = [
                self.page.get_by_role("button", name=re.compile(re.escape(text))),
                self.page.get_by_text(text, exact=False),
            ]
            for locator in locators:
                try:
                    count = min(await locator.count(), 8)
                    for index in range(count):
                        item = locator.nth(index)
                        if await _is_visible(item):
                            await item.click(timeout=timeout)
                            await self.page.wait_for_timeout(300)
                            return text
                except Exception as exc:  # Playwright can throw on stale locators.
                    errors.append(str(exc))
        raise BrowserBackendError(
            f"could not find clickable text from {list(candidates)}"
            + (f"; last error: {errors[-1]}" if errors else "")
        )

    async def click_action(self, action: str) -> dict[str, Any]:
        try:
            text = await self.click_text(ACTION_TEXTS[action])
            return {"method": "text", "clicked": text}
        except BrowserBackendError as text_error:
            if action not in RIGHT_RAIL_ACTION_SLOTS:
                raise
            try:
                return await self._click_right_rail_action(action)
            except BrowserBackendError as rail_error:
                raise BrowserBackendError(f"{text_error}; right rail fallback failed: {rail_error}") from rail_error

    async def _click_right_rail_action(self, action: str) -> dict[str, Any]:
        slot = RIGHT_RAIL_ACTION_SLOTS[action]
        target = await self.page.evaluate(
            """
            (slot) => {
              const players = Array.from(document.querySelectorAll(
                '.playerContainer,.basePlayerContainer,.slider-video,[class*="playerContainer"],[class*="basePlayerContainer"]'
              )).map((el) => {
                const bounds = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return { bounds, visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 };
              }).filter((item) => (
                item.visible
                  && item.bounds.width > 200
                  && item.bounds.height > 200
                  && item.bounds.top < window.innerHeight
                  && item.bounds.bottom > 0
                  && item.bounds.left < window.innerWidth * 0.85
              )).sort((a, b) => (
                Math.abs(a.bounds.top) - Math.abs(b.bounds.top)
                  || (b.bounds.width * b.bounds.height) - (a.bounds.width * a.bounds.height)
              ));
              const rect = players[0] ? players[0].bounds : { top: 0, right: window.innerWidth * 0.72, bottom: window.innerHeight };
              const minX = Math.max(0, rect.right - 120);
              const maxX = Math.min(window.innerWidth, rect.right + 24);
              const minY = Math.max(0, rect.top + 80);
              const maxY = Math.min(window.innerHeight, rect.bottom + 120);
              const countLikeText = (text) => /[0-9０-９万亿]/.test(text) && text.length <= 16;
              const isVisible = (style, bounds) => (
                style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity) > 0
                  && bounds.width >= 24
                  && bounds.width <= 90
                  && bounds.height >= 40
                  && bounds.height <= 110
              );
              const groups = Array.from(document.querySelectorAll('div,a,button,[role="button"]')).map((el) => {
                const bounds = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                return {
                  text,
                  x: bounds.x,
                  y: bounds.y,
                  w: bounds.width,
                  h: bounds.height,
                  cx: bounds.x + bounds.width / 2,
                  cy: bounds.y + bounds.height / 2,
                  cursor: style.cursor,
                  visible: isVisible(style, bounds),
                };
              }).filter((item) => (
                item.visible
                  && item.cx >= minX
                  && item.cx <= maxX
                  && item.cy >= minY
                  && item.cy <= maxY
                  && countLikeText(item.text)
              )).sort((a, b) => a.y - b.y || a.x - b.x);

              const unique = [];
              for (const item of groups) {
                if (!unique.some((seen) => Math.abs(seen.cx - item.cx) < 3 && Math.abs(seen.cy - item.cy) < 12)) {
                  unique.push(item);
                }
              }
              const item = unique[slot];
              if (!item) {
                return { ok: false, candidates: unique.slice(0, 8), player: rect ? { right: rect.right, top: rect.top, bottom: rect.bottom } : null };
              }
              return {
                ok: true,
                x: Math.round(item.cx),
                y: Math.round(item.y + Math.min(24, item.h * 0.36)),
                slot,
                text: item.text,
                candidates: unique.slice(0, 8),
              };
            }
            """,
            slot,
        )
        if not target.get("ok"):
            raise BrowserBackendError(f"could not infer right rail {action} button: {target}")
        await self.page.mouse.click(target["x"], target["y"])
        await self.page.wait_for_timeout(500)
        result = {"method": "right-rail", "action": action, **target}
        if action == "like":
            result["liked"] = await self._current_like_active()
            if not result["liked"]:
                raise BrowserBackendError(f"like click did not produce an active liked state: {result}")
        return result

    async def dismiss_prompts(self) -> dict[str, Any]:
        clicked = []
        with contextlib.suppress(BrowserBackendError):
            clicked.append(await self.click_text(["我知道了", "知道了"], timeout=900))
        await self.press("Escape")
        with contextlib.suppress(BrowserBackendError):
            clicked.append(await self.click_text(["关闭", "取消"], timeout=900))
        return {"clicked": clicked, "pressed": ["Escape"]}

    async def click_visible_text(self, text: str) -> dict[str, Any]:
        clicked = await self.click_text([text])
        return {"clicked": clicked}

    async def press(self, key: str) -> dict[str, Any]:
        await self.page.keyboard.press(key)
        await self.page.wait_for_timeout(300)
        return {"key": key}

    async def navigate_video(self, direction: str) -> dict[str, Any]:
        if direction not in {"next", "prev"}:
            raise BrowserBackendError("video navigation direction must be next or prev")
        before = await self.video_state()
        key = "ArrowDown" if direction == "next" else "ArrowUp"
        await self.press(key)
        await self.page.wait_for_timeout(800)
        after = await self.video_state()
        return {"direction": direction, "key": key, "before": before, "after": after}

    async def screenshot(self, output: Path) -> dict[str, Any]:
        output.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(output), full_page=False)
        return {"path": str(output), "url": self.page.url}

    async def login_status(self) -> dict[str, Any]:
        body_text = await self._safe_body_text()
        cookies = await self.context.cookies("https://www.douyin.com/")
        cookie_names = {cookie.get("name") for cookie in cookies}
        status, markers = infer_login_status(body_text, cookie_names)
        return {
            "status": status,
            "url": self.page.url,
            "title": await self.page.title(),
            "markers": markers,
        }

    async def wait_login(self, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds
        last_status = None
        while time.time() < deadline:
            last_status = await self.login_status()
            if last_status["status"] == "logged_in":
                return last_status
            await self.page.wait_for_timeout(1000)
        return last_status or {"status": "unknown", "url": self.page.url}

    async def video_state(self) -> dict[str, Any]:
        await self._ensure_video_picker()
        return await self.page.evaluate(
            """
            () => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              return {
                exists: true,
                paused: video.paused,
                muted: video.muted,
                currentTime: video.currentTime,
                duration: Number.isFinite(video.duration) ? video.duration : null,
                width: video.videoWidth,
                height: video.videoHeight,
                readyState: video.readyState
              };
            }
            """
        )

    async def seek_video(self, seconds: float | None = None, percent: float | None = None) -> dict[str, Any]:
        before = await self.video_state()
        if not before.get("exists"):
            raise BrowserBackendError("no video element found on the current page")
        if seconds is None and percent is None:
            raise BrowserBackendError("provide seconds or percent")
        result = await self.page.evaluate(
            """
            ({ seconds, percent }) => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              const duration = Number.isFinite(video.duration) ? video.duration : null;
              let target = seconds;
              if (target === null || target === undefined) {
                if (!duration) return { exists: true, error: 'duration is unavailable' };
                target = duration * percent / 100;
              }
              target = Math.max(0, duration ? Math.min(duration, target) : target);
              video.currentTime = target;
              return { exists: true, targetTime: target, duration, currentTime: video.currentTime };
            }
            """,
            {"seconds": seconds, "percent": percent},
        )
        await self.page.wait_for_timeout(500)
        return {"before": before, "result": result, "after": await self.video_state()}

    async def set_rate(self, rate: float) -> dict[str, Any]:
        if rate <= 0 or rate > 16:
            raise BrowserBackendError("playback rate must be between 0 and 16")
        before = await self.video_state()
        result = await self.page.evaluate(
            """
            (rate) => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              video.playbackRate = rate;
              return { exists: true, playbackRate: video.playbackRate };
            }
            """,
            rate,
        )
        await self.page.wait_for_timeout(300)
        return {"before": before, "result": result, "after": await self.video_state()}

    async def set_volume(self, volume: float) -> dict[str, Any]:
        if volume < 0 or volume > 1:
            raise BrowserBackendError("volume must be between 0 and 1")
        before = await self.video_state()
        result = await self.page.evaluate(
            """
            (volume) => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              video.volume = volume;
              video.muted = volume === 0;
              return { exists: true, volume: video.volume, muted: video.muted };
            }
            """,
            volume,
        )
        await self.page.wait_for_timeout(300)
        return {"before": before, "result": result, "after": await self.video_state()}

    async def set_playback(self, mode: str) -> dict[str, Any]:
        if mode == "state":
            return await self.video_state()
        before = await self.video_state()
        if not before.get("exists"):
            raise BrowserBackendError("no video element found on the current page")
        await self._ensure_video_picker()
        js_mode = mode
        result = await self.page.evaluate(
            """
            async (mode) => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              try {
                if (mode === 'pause') video.pause();
                if (mode === 'resume') await video.play();
                if (mode === 'toggle') {
                  if (video.paused) await video.play();
                  else video.pause();
                }
              } catch (error) {
                return { exists: true, error: String(error), paused: video.paused };
              }
              return { exists: true, paused: video.paused, muted: video.muted, currentTime: video.currentTime };
            }
            """,
            js_mode,
        )
        if result.get("error") and mode in {"resume", "toggle"}:
            await self.press("Space")
            result = await self.video_state()
        await self.page.wait_for_timeout(300)
        after = await self.video_state()
        return {"before": before, "result": result, "after": after}

    async def sound(self, mode: str) -> dict[str, Any]:
        if mode not in {"on", "off", "toggle"}:
            raise BrowserBackendError("sound mode must be on, off, or toggle")
        before = await self.video_state()
        if not before.get("exists"):
            raise BrowserBackendError("no video element found on the current page")
        await self._ensure_video_picker()
        result = await self.page.evaluate(
            """
            (mode) => {
              const video = pickDouyinVideo();
              if (!video) return { exists: false };
              if (mode === 'on') {
                video.muted = false;
                video.volume = 1;
              } else if (mode === 'off') {
                video.muted = true;
              } else if (mode === 'toggle') {
                video.muted = !video.muted;
                if (!video.muted && video.volume === 0) video.volume = 1;
              }
              return { exists: true, muted: video.muted, volume: video.volume };
            }
            """,
            mode,
        )
        clicked = None
        if mode == "on":
            with contextlib.suppress(BrowserBackendError):
                clicked = await self.click_text(ACTION_TEXTS["sound"], timeout=1200)
        after = await self.video_state()
        return {"mode": mode, "before": before, "result": result, "clicked": clicked, "after": after}

    async def fullscreen(self) -> dict[str, Any]:
        try:
            clicked = await self.click_text(ACTION_TEXTS["fullscreen"], timeout=1200)
            return {"method": "text", "clicked": clicked}
        except BrowserBackendError:
            await self.press("f")
            return {"method": "keyboard", "key": "f"}

    async def clean_screen(self) -> dict[str, Any]:
        return await self.click_action("clean")

    async def danmaku(self, mode: str) -> dict[str, Any]:
        if mode not in {"on", "off", "toggle"}:
            raise BrowserBackendError("danmaku mode must be on, off, or toggle")
        if mode in {"on", "off"}:
            with contextlib.suppress(BrowserBackendError):
                option = await self._click_danmaku_option(mode)
                return {"mode": mode, "method": "settings-option", **option, "note": "Douyin does not expose a stable public danmaku state; verify visually."}
        target = await self.page.evaluate(
            """
            () => {
              const inViewport = (item) => (
                item.cx >= 0
                  && item.cx <= window.innerWidth
                  && item.cy >= 0
                  && item.cy <= window.innerHeight
              );
              const visibleElement = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return {
                  el,
                  x: rect.x,
                  y: rect.y,
                  w: rect.width,
                  h: rect.height,
                  cx: rect.x + rect.width / 2,
                  cy: rect.y + rect.height / 2,
                  cls: String(el.className),
                  text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '),
                  opacity: style.opacity,
                  display: style.display,
                  visibility: style.visibility,
                };
              };
              const isVisible = (item) => (
                item.w >= 20
                  && item.h >= 20
                  && item.display !== 'none'
                  && item.visibility !== 'hidden'
                  && Number(item.opacity) > 0
                  && inViewport(item)
              );
              const inputBars = Array.from(document.querySelectorAll('.danmakuContainer, [class*="danmakuInputContainer"]'))
                .map(visibleElement)
                .filter((item) => isVisible(item) && item.w >= 180)
                .sort((a, b) => b.y - a.y || a.x - b.x);
              for (const bar of inputBars) {
                const icons = Array.from(document.querySelectorAll('div,span,button'))
                  .map(visibleElement)
                  .filter((item) => (
                    isVisible(item)
                      && item.w <= 40
                      && item.h <= 40
                      && item.cx >= bar.x - 90
                      && item.cx < bar.x + 80
                      && Math.abs(item.cy - bar.cy) <= 8
                      && !item.cls.includes('CahWcRNr')
                  ))
                  .sort((a, b) => {
                    const aSettings = a.text.includes('弹幕设置') ? 1 : 0;
                    const bSettings = b.text.includes('弹幕设置') ? 1 : 0;
                    return bSettings - aSettings || b.cx - a.cx;
                  });
                const item = icons[0];
                if (item) {
                  return {
                    ok: true,
                    x: Math.round(item.cx),
                    y: Math.round(item.cy),
                    cls: item.cls,
                    opacity: item.opacity,
                    method: 'danmaku-input-leading-icon',
                    candidates: icons.slice(0, 6).map(({el, ...rest}) => rest),
                  };
                }
              }
              const candidates = Array.from(document.querySelectorAll('.danmakuContainer, [class*="danmaku"]'));
              const visible = candidates.map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return {
                  x: rect.x,
                  y: rect.y,
                  w: rect.width,
                  h: rect.height,
                  cx: rect.x + rect.width / 2,
                  cy: rect.y + rect.height / 2,
                  cls: String(el.className),
                  opacity: style.opacity,
                  display: style.display,
                  visibility: style.visibility,
                };
              }).filter((item) => (
                isVisible(item)
              )).sort((a, b) => b.y - a.y || a.x - b.x);
              const item = visible[0];
              if (!item) return { ok: false, candidates: visible };
              return {
                ok: true,
                x: Math.round(item.cx),
                y: Math.round(item.cy),
                cls: item.cls,
                opacity: item.opacity,
                candidates: visible.slice(0, 6),
              };
            }
            """
        )
        if not target.get("ok"):
            raise BrowserBackendError(f"could not infer danmaku control: {target}")
        await self.page.mouse.click(target["x"], target["y"])
        await self.page.wait_for_timeout(500)
        if mode in {"on", "off"}:
            try:
                option = await self._click_danmaku_option(mode)
            except BrowserBackendError as exc:
                option = {"ok": False, "message": str(exc)}
            return {"mode": mode, "method": "player-control", "control": target, "option": option, "note": "Douyin does not expose a stable public danmaku state; verify visually."}
        return {"mode": mode, "method": "player-control", **target, "note": "Douyin does not expose a stable public danmaku state; verify visually."}

    async def _click_danmaku_option(self, mode: str) -> dict[str, Any]:
        label = "关闭" if mode == "off" else "全部"
        target = await self.page.evaluate(
            """
            (label) => {
              const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 4
                  && rect.height > 4
                  && style.display !== 'none'
                  && style.visibility !== 'hidden'
                  && Number(style.opacity) > 0;
              };
              const panels = Array.from(document.querySelectorAll('div')).map((el) => {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                return { el, rect, text };
              }).filter((item) => (
                visible(item.el)
                  && item.text.includes('弹幕开关')
                  && item.text.includes('关闭')
                  && item.text.includes('全部')
              )).sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
              const panel = panels[0]?.el;
              if (!panel) return { ok: false, label, reason: 'settings panel not found' };
              const nodes = Array.from(panel.querySelectorAll('span,div,button')).map((el) => {
                const rect = el.getBoundingClientRect();
                const text = (el.innerText || el.textContent || '').trim();
                const style = window.getComputedStyle(el);
                return {
                  text,
                  x: rect.x,
                  y: rect.y,
                  w: rect.width,
                  h: rect.height,
                  cx: rect.x + rect.width / 2,
                  cy: rect.y + rect.height / 2,
                  color: style.color,
                };
              }).filter((item) => item.text === label && item.w > 4 && item.h > 4)
                .sort((a, b) => a.y - b.y || a.x - b.x);
              const item = nodes[0];
              if (!item) return { ok: false, label, reason: 'option not found' };
              return { ok: true, label, x: Math.round(item.cx), y: Math.round(item.cy), color: item.color };
            }
            """,
            label,
        )
        if not target.get("ok"):
            raise BrowserBackendError(f"could not find danmaku option: {target}")
        await self.page.mouse.click(target["x"], target["y"])
        await self.page.wait_for_timeout(250)
        with contextlib.suppress(Exception):
            await self.press("Escape")
        return target

    async def prepare_playback(self) -> dict[str, Any]:
        steps = []
        with contextlib.suppress(BrowserBackendError):
            await self.click_text(["取消清屏"], timeout=900)
        for name, action in [
            ("sound-on", lambda: self.sound("on")),
            ("danmaku-off", lambda: self.danmaku("off")),
            ("clean", lambda: self.click_text(["清屏"])),
            ("fullscreen", self.fullscreen),
        ]:
            try:
                data = await action()
                steps.append({"action": name, "ok": True, "data": data})
            except Exception as exc:
                steps.append({"action": name, "ok": False, "message": str(exc)})
        return {"steps": steps, "video": await self.video_state(), "url": self.page.url}

    async def toggle_loop(self) -> dict[str, Any]:
        clicked = await self.click_text(["连播"], timeout=1200)
        return {"clicked": clicked, "note": "Douyin does not expose a stable public loop state; verify visually."}

    async def comments(self, mode: str) -> dict[str, Any]:
        if mode not in {"open", "close", "toggle"}:
            raise BrowserBackendError("comments mode must be open, close, or toggle")
        before = await self._comment_panel_open()
        if mode == "open" or (mode == "toggle" and not before):
            await self.click_action("comment")
            await self.page.wait_for_timeout(700)
        elif mode == "close" or (mode == "toggle" and before):
            await self._close_side_panel()
        after = await self._comment_panel_open()
        return {"mode": mode, "before_open": before, "after_open": after}

    async def _close_side_panel(self) -> dict[str, Any]:
        target = await self.page.evaluate(
            """
            () => {
              const items = Array.from(document.querySelectorAll('div,button,span,svg')).map((el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const text = (el.innerText || el.textContent || '').trim();
                return {
                  x: rect.x,
                  y: rect.y,
                  w: rect.width,
                  h: rect.height,
                  cx: rect.x + rect.width / 2,
                  cy: rect.y + rect.height / 2,
                  text,
                  cls: String(el.className),
                  display: style.display,
                  visibility: style.visibility,
                  opacity: style.opacity,
                };
              }).filter((item) => (
                item.w >= 12
                  && item.w <= 48
                  && item.h >= 12
                  && item.h <= 48
                  && item.cx > window.innerWidth - 160
                  && item.cy >= 56
                  && item.cy < 130
                  && item.display !== 'none'
                  && item.visibility !== 'hidden'
                  && Number(item.opacity) > 0
              )).sort((a, b) => {
                const aClose = a.cls.includes('KhyY7h5W') ? 1 : 0;
                const bClose = b.cls.includes('KhyY7h5W') ? 1 : 0;
                return bClose - aClose || b.cx - a.cx || a.cy - b.cy;
              });
              return items[0] ? { ok: true, ...items[0] } : { ok: false, candidates: items.slice(0, 10) };
            }
            """
        )
        if target.get("ok"):
            await self.page.mouse.click(target["cx"], target["cy"])
            await self.page.wait_for_timeout(1000)
            return target
        await self.press("Escape")
        return target

    async def send_danmaku(self, text: str, submit: bool = False) -> dict[str, Any]:
        editor = await self._find_danmaku_editor()
        if not editor:
            raise BrowserBackendError("could not find danmaku editor")
        await editor.click(timeout=2000)
        with contextlib.suppress(Exception):
            await editor.fill("")
        await editor.type(text, delay=15)
        submitted = False
        if submit:
            with contextlib.suppress(BrowserBackendError):
                await self.click_text(["发送"], timeout=1000)
                submitted = True
            if not submitted:
                await self.page.keyboard.press("Enter")
                submitted = True
            await self.page.wait_for_timeout(500)
        return {"text": text, "submitted": submitted}

    async def comment(self, text: str, submit: bool = False) -> dict[str, Any]:
        if not await self._comment_panel_open():
            await self.click_action("comment")
            await self.page.wait_for_timeout(500)
        editor = await self._find_comment_editor()
        focused_placeholder = False
        if not editor:
            focused_placeholder = await self._focus_comment_box()
        if not editor and not focused_placeholder:
            raise BrowserBackendError("could not find a comment editor")
        if editor:
            await editor.click(timeout=3000)
            with contextlib.suppress(Exception):
                await editor.fill("")
            await editor.type(text, delay=15)
        else:
            await self.page.keyboard.type(text, delay=15)
        submitted = False
        if submit:
            submitted = await self._submit_comment()
        return {"text": text, "submitted": submitted, "focused_placeholder": focused_placeholder}

    async def _submit_comment(self) -> bool:
        before = await self._comment_editor_text()
        for selector in [
            ".commentInput-right-ct span:last-child",
            ".commentInput-right-ct [role='button']:last-child",
            ".comment-input-container span:last-child",
        ]:
            try:
                locator = self.page.locator(selector).last
                if await _is_visible(locator):
                    await locator.click(timeout=1500)
                    await self.page.wait_for_timeout(1200)
                    if await self._comment_submission_confirmed(before):
                        return True
            except Exception:
                pass
        for key in ["Meta+Enter", "Control+Enter", "Enter"]:
            try:
                await self.page.keyboard.press(key)
                await self.page.wait_for_timeout(1200)
                if await self._comment_submission_confirmed(before):
                    return True
            except Exception:
                pass
        with contextlib.suppress(BrowserBackendError):
            await self.click_text(["发布"], timeout=1000)
            await self.page.wait_for_timeout(1200)
            if await self._comment_submission_confirmed(before):
                return True
        return False

    async def _comment_submission_confirmed(self, before: str) -> bool:
        current = await self._comment_editor_text()
        return bool(before) and current == ""

    async def _comment_editor_text(self) -> str:
        with contextlib.suppress(Exception):
            return str(await self.page.evaluate(
                """
                () => {
                  const editor = document.querySelector(
                    '.comment-input-container [contenteditable="true"], .public-DraftEditor-content[contenteditable="true"]'
                  );
                  return editor ? (editor.innerText || editor.textContent || '').trim() : '';
                }
                """
            ))
        return ""

    async def _current_like_active(self) -> bool:
        with contextlib.suppress(Exception):
            return bool(await self.page.evaluate(
                """
                () => {
                  const players = Array.from(document.querySelectorAll(
                    '.playerContainer,.basePlayerContainer,.slider-video,[class*="playerContainer"],[class*="basePlayerContainer"]'
                  )).map((el) => {
                    const bounds = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return { bounds, visible: style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > 0 };
                  }).filter((item) => (
                    item.visible
                      && item.bounds.width > 200
                      && item.bounds.height > 200
                      && item.bounds.top < window.innerHeight
                      && item.bounds.bottom > 0
                  )).sort((a, b) => Math.abs(a.bounds.top) - Math.abs(b.bounds.top));
                  const right = players[0] ? players[0].bounds.right : window.innerWidth * 0.72;
                  const items = Array.from(document.querySelectorAll('div,a,button,[role="button"]')).filter((el) => {
                    const bounds = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const text = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                    return bounds.x >= right - 130
                      && bounds.x <= right + 30
                      && bounds.y >= 400
                      && bounds.y <= 560
                      && bounds.width >= 24
                      && bounds.height >= 40
                      && /[0-9０-９万亿]/.test(text)
                      && style.display !== 'none'
                      && style.visibility !== 'hidden'
                      && Number(style.opacity) > 0;
                  });
                  return items.some((el) => /取消点赞|已点赞/.test(el.innerText || el.textContent || ''))
                    || items.some((el) => Array.from(el.querySelectorAll('path')).some((path) => {
                      const fill = window.getComputedStyle(path).fill;
                      return /254, 44, 85|255, 44, 85/.test(fill);
                    }));
                }
                """
            ))
        return False

    async def _find_comment_editor(self):
        editor = await self._find_editable_node()
        if editor:
            return editor
        await self._focus_comment_box()
        await self.page.wait_for_timeout(300)
        return await self._find_editable_node()

    async def _find_editable_node(self):
        selectors = [
            "textarea",
            "input[placeholder*='评论']",
            "textarea[placeholder*='评论']",
            "[placeholder*='评论']",
            "[contenteditable='true']",
            "[contenteditable='plaintext-only']",
            "[contenteditable]:not([contenteditable='false'])",
            "[role='textbox']",
        ]
        for selector in selectors:
            locator = self.page.locator(selector)
            try:
                count = min(await locator.count(), 8)
                for index in range(count):
                    item = locator.nth(index)
                    if await _is_visible(item):
                        return item
            except Exception:
                pass
        return None

    async def _find_danmaku_editor(self):
        selectors = [
            ".danmakuInputContainer input",
            ".danmakuContainer input",
            "input[class*='Mq_tyWgd']",
        ]
        for selector in selectors:
            locator = self.page.locator(selector)
            try:
                count = min(await locator.count(), 8)
                for index in range(count):
                    item = locator.nth(index)
                    if await _is_visible(item):
                        return item
            except Exception:
                pass
        return None

    async def _focus_comment_box(self) -> bool:
        locators = [
            self.page.get_by_text("留下你的精彩评论吧", exact=False),
            self.page.locator(".comment-input-container"),
            self.page.locator("[class*='comment-input']"),
        ]
        for locator in locators:
            try:
                count = min(await locator.count(), 6)
                for index in range(count):
                    item = locator.nth(index)
                    if await _is_visible(item):
                        await item.click(timeout=1500)
                        await self.page.wait_for_timeout(300)
                        return True
            except Exception:
                pass
        return False

    async def _comment_panel_open(self) -> bool:
        try:
            return bool(await self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('div,span')).some((el) => {
                  const rect = el.getBoundingClientRect();
                  const style = window.getComputedStyle(el);
                  const text = (el.innerText || el.textContent || '').trim();
                  const hit = document.elementFromPoint(rect.x + Math.min(rect.width / 2, 12), rect.y + Math.min(rect.height / 2, 12));
                  return /全部评论\\(/.test(text)
                    && rect.width > 4
                    && rect.height > 4
                    && rect.x > window.innerWidth * 0.55
                    && rect.x < window.innerWidth
                    && rect.y > 80
                    && rect.y < window.innerHeight
                    && hit
                    && (el.contains(hit) || hit.contains(el))
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity) > 0;
                })
                """
            ))
        except Exception:
            pass
        return False

    async def _safe_body_text(self) -> str:
        try:
            body = self.page.locator("body")
            return await body.inner_text(timeout=2500)
        except Exception:
            return ""


async def _is_visible(locator) -> bool:
    try:
        return await locator.is_visible(timeout=600)
    except TypeError:
        return await locator.is_visible()
    except Exception:
        return False


def _read_json(url: str, timeout: float) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BrowserBackendError(str(exc)) from exc


def _which(command: str) -> Optional[str]:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        path = Path(folder) / command
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return None


def activate_browser_app() -> dict[str, Any]:
    if sys.platform != "darwin":
        return {"ok": False, "method": "osascript", "reason": "activation is only implemented on macOS"}
    completed = subprocess.run(  # noqa: S603
        ["osascript", "-e", 'tell application "Google Chrome" to activate'],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "method": "osascript",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


VIDEO_PICKER_SCRIPT = """
() => {
  if (window.pickDouyinVideo) return;
  window.pickDouyinVideo = () => {
    const videos = Array.from(document.querySelectorAll('video'));
    const scored = videos.map((video, index) => {
      const rect = video.getBoundingClientRect();
      const visibleArea = Math.max(0, Math.min(rect.right, window.innerWidth) - Math.max(rect.left, 0))
        * Math.max(0, Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0));
      return {
        video,
        score: visibleArea + video.readyState * 100000 + (video.videoWidth || 0) + (video.videoHeight || 0) - index,
      };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored[0]?.video || null;
  };
}
"""


def infer_login_status(body_text: str, cookie_names: set[str]) -> tuple[str, dict[str, Any]]:
    account_text = any(marker in body_text for marker in LOGIN_ACCOUNT_MARKERS)
    login_text = any(marker in body_text for marker in LOGIN_BUTTON_MARKERS)
    strong_cookie_names = sorted(cookie_names & set(LOGIN_COOKIE_MARKERS))
    cookie_login = bool(strong_cookie_names)
    if account_text or cookie_login:
        status = "logged_in"
    elif login_text:
        status = "logged_out"
    else:
        status = "unknown"
    return status, {
        "account_text": account_text,
        "login_text": login_text,
        "cookie_login": cookie_login,
        "login_cookie_names": strong_cookie_names,
    }


# Imported late to keep the text markers close to the detector.
from ..core.config import LOGIN_ACCOUNT_MARKERS, LOGIN_BUTTON_MARKERS  # noqa: E402

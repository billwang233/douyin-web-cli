from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shlex
import sys

import click

from .core import actions
from .core.config import FEED_URLS, feed_url, home_dir
from .core.state import ActionResult, append_history
from .utils.recording import list_avfoundation_devices, record_avfoundation


def main() -> None:
    cli()


@click.group(invoke_without_command=True)
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--home", type=click.Path(file_okay=False, dir_okay=True), help="Override DOUYIN_WEB_HOME.")
@click.option("--screenshot/--no-screenshot", default=True, show_default=True, help="Capture the viewport after page actions.")
@click.option("--screenshot-dir", type=click.Path(file_okay=False, dir_okay=True, path_type=Path), help="Directory for automatic screenshots.")
@click.pass_context
def cli(
    ctx: click.Context,
    json_output: bool,
    home: str | None,
    screenshot: bool,
    screenshot_dir: Path | None,
) -> None:
    """Control Douyin web from the terminal."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    ctx.obj["home"] = home
    ctx.obj["auto_screenshot"] = screenshot
    ctx.obj["screenshot_dir"] = screenshot_dir
    if ctx.invoked_subcommand is None:
        repl(ctx)


@cli.command()
@click.argument("target", default="recommend", required=False)
@click.option("--port", type=int, help="Remote debugging port.")
@click.option("--browser-path", type=click.Path(exists=True), help="Chrome/Chromium executable.")
@click.option("--user-data-dir", type=click.Path(file_okay=False, dir_okay=True), help="Browser profile directory.")
@click.pass_context
def launch(ctx: click.Context, target: str, port: int | None, browser_path: str | None, user_data_dir: str | None) -> None:
    """Launch a controllable Chrome/Chromium session."""
    result = actions.launch(
        url=feed_url(target),
        home=ctx.obj["home"],
        port=port,
        browser_path=browser_path,
        user_data_dir=user_data_dir,
    )
    emit(ctx, result)


@cli.command(name="close")
@click.pass_context
def close_cmd(ctx: click.Context) -> None:
    """Terminate the launched browser process when possible and clear state."""
    emit(ctx, actions.close(home=ctx.obj["home"]))


@cli.command(name="state")
@click.pass_context
def state_cmd(ctx: click.Context) -> None:
    """Show saved browser session state."""
    emit(ctx, actions.state(home=ctx.obj["home"]))


@cli.command(name="open")
@click.argument("target", default="recommend", required=False)
@click.option("--no-auto-launch", is_flag=True, help="Fail instead of launching a browser automatically.")
@click.pass_context
def open_cmd(ctx: click.Context, target: str, no_auto_launch: bool) -> None:
    """Open a Douyin feed or URL."""
    emit(ctx, actions.open_feed(target, home=ctx.obj["home"], auto_launch=not no_auto_launch))


@cli.command()
@click.argument("target", type=click.Choice(sorted(FEED_URLS)), default="recommend", required=False)
@click.pass_context
def feed(ctx: click.Context, target: str) -> None:
    """Open a named feed."""
    emit(ctx, actions.open_feed(target, home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def current(ctx: click.Context) -> None:
    """Show current page, login, and video state."""
    emit(ctx, actions.current(home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Extract visible metadata for the current video."""
    emit(ctx, actions.info(home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def focus(ctx: click.Context) -> None:
    """Bring the Douyin browser window to the front."""
    emit(ctx, actions.focus(home=ctx.obj["home"]))


@cli.command(name="reload")
@click.pass_context
def reload_cmd(ctx: click.Context) -> None:
    """Reload the current Douyin page."""
    emit(ctx, actions.reload_page(home=ctx.obj["home"]))


@cli.command()
@click.argument("query")
@click.option("--submit/--no-submit", default=True, show_default=True, help="Submit the search after typing.")
@click.pass_context
def search(ctx: click.Context, query: str, submit: bool) -> None:
    """Type into Douyin search and optionally submit."""
    emit(ctx, actions.search(query=query, submit=submit, home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Check login state."""
    emit(ctx, actions.login_status(home=ctx.obj["home"]))


@cli.command("wait-login")
@click.option("--timeout", "timeout_seconds", type=int, default=300, show_default=True)
@click.pass_context
def wait_login_cmd(ctx: click.Context, timeout_seconds: int) -> None:
    """Wait while the user logs in manually in the browser."""
    emit(ctx, actions.wait_login(timeout_seconds=timeout_seconds, home=ctx.obj["home"]))


@cli.command()
@click.argument("mode", type=click.Choice(["state", "pause", "resume", "toggle"]), default="state", required=False)
@click.pass_context
def play(ctx: click.Context, mode: str) -> None:
    """Inspect or control the current video playback state."""
    emit(ctx, actions.player_action(mode, home=ctx.obj["home"]))


@cli.command()
@click.argument("mode", type=click.Choice(["on", "off", "toggle"]), default="toggle", required=False)
@click.pass_context
def sound(ctx: click.Context, mode: str) -> None:
    """Turn current video sound on/off or toggle mute."""
    emit(ctx, actions.sound_action(mode, home=ctx.obj["home"]))


@cli.command()
@click.option("--seconds", type=float, help="Seek to an absolute timestamp.")
@click.option("--percent", type=float, help="Seek to a percentage of the current video duration.")
@click.pass_context
def seek(ctx: click.Context, seconds: float | None, percent: float | None) -> None:
    """Seek within the current video."""
    emit(ctx, actions.seek(seconds=seconds, percent=percent, home=ctx.obj["home"]))


@cli.command()
@click.argument("value", type=float)
@click.pass_context
def rate(ctx: click.Context, value: float) -> None:
    """Set the current video's playback rate."""
    emit(ctx, actions.rate(value, home=ctx.obj["home"]))


@cli.command()
@click.argument("value", type=float)
@click.pass_context
def volume(ctx: click.Context, value: float) -> None:
    """Set current video volume from 0.0 to 1.0."""
    emit(ctx, actions.volume(value, home=ctx.obj["home"]))


@cli.command(name="next")
@click.pass_context
def next_cmd(ctx: click.Context) -> None:
    """Move to the next feed video."""
    emit(ctx, actions.navigate_video("next", home=ctx.obj["home"]))


@cli.command(name="prev")
@click.pass_context
def prev_cmd(ctx: click.Context) -> None:
    """Move to the previous feed video."""
    emit(ctx, actions.navigate_video("prev", home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def fullscreen(ctx: click.Context) -> None:
    """Enter Douyin player fullscreen when available."""
    emit(ctx, actions.text_action("fullscreen", home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def clean(ctx: click.Context) -> None:
    """Click Douyin's clean-screen control."""
    emit(ctx, actions.text_action("clean", home=ctx.obj["home"]))


@cli.command()
@click.argument("mode", type=click.Choice(["on", "off", "toggle"]), default="toggle", required=False)
@click.pass_context
def danmaku(ctx: click.Context, mode: str) -> None:
    """Toggle or request a danmaku state."""
    emit(ctx, actions.text_action("danmaku", home=ctx.obj["home"], mode=mode))


@cli.command("danmaku-send")
@click.argument("text")
@click.option("--submit/--no-submit", default=False, show_default=True, help="Submit after typing.")
@click.pass_context
def danmaku_send_cmd(ctx: click.Context, text: str, submit: bool) -> None:
    """Type a danmaku message into the current video."""
    emit(ctx, actions.danmaku_send(text=text, submit=submit, home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def loop(ctx: click.Context) -> None:
    """Toggle Douyin auto-play/continuous play."""
    emit(ctx, actions.text_action("loop", home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def prepare(ctx: click.Context) -> None:
    """Prepare the current video for clean playback or recording."""
    emit(ctx, actions.prepare(home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def dismiss(ctx: click.Context) -> None:
    """Dismiss common Douyin prompts and overlays."""
    emit(ctx, actions.dismiss(home=ctx.obj["home"]))


@cli.command(name="click-text")
@click.argument("text")
@click.pass_context
def click_text_cmd(ctx: click.Context, text: str) -> None:
    """Click visible text in the current Douyin page."""
    emit(ctx, actions.click_text(text, home=ctx.obj["home"]))


@cli.command()
@click.argument("mode", type=click.Choice(["open", "close", "toggle"]), default="toggle", required=False)
@click.pass_context
def comments(ctx: click.Context, mode: str) -> None:
    """Open, close, or toggle the current video's comments panel."""
    emit(ctx, actions.comments(mode=mode, home=ctx.obj["home"]))


@cli.command()
@click.argument("key")
@click.pass_context
def press(ctx: click.Context, key: str) -> None:
    """Press a keyboard key or key chord in the Douyin page."""
    emit(ctx, actions.press(key=key, home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def like(ctx: click.Context) -> None:
    """Click the current video's like control."""
    emit(ctx, actions.text_action("like", home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def favorite(ctx: click.Context) -> None:
    """Click the current video's favorite/collect control."""
    emit(ctx, actions.text_action("favorite", home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def share(ctx: click.Context) -> None:
    """Click the current video's share control."""
    emit(ctx, actions.text_action("share", home=ctx.obj["home"]))


@cli.command()
@click.argument("text")
@click.option("--submit/--no-submit", default=False, show_default=True, help="Submit after typing.")
@click.pass_context
def comment(ctx: click.Context, text: str, submit: bool) -> None:
    """Type a comment into the current video's comment box."""
    emit(ctx, actions.comment(text=text, submit=submit, home=ctx.obj["home"]))


@cli.command()
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def screenshot(ctx: click.Context, output: Path) -> None:
    """Capture the current Douyin viewport."""
    emit(ctx, actions.screenshot(output=output, home=ctx.obj["home"]))


@cli.command()
@click.pass_context
def devices(ctx: click.Context) -> None:
    """List AVFoundation video/audio devices for recording."""
    emit(ctx, list_avfoundation_devices())


@cli.command()
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--duration", type=float, default=15.0, show_default=True)
@click.option("--video-index", type=int, required=True, help="AVFoundation video device index.")
@click.option("--audio-index", type=int, required=True, help="AVFoundation audio device index. Prefer BlackHole 2ch.")
@click.option("--fps", type=int, default=30, show_default=True)
@click.option("--scale-width", type=int, help="Optional output video width, keeping aspect ratio.")
@click.option("--verify", is_flag=True, help="Run ffprobe and volumedetect after recording.")
@click.option("--dry-run", is_flag=True, help="Print the ffmpeg command without recording.")
@click.option("--allow-non-blackhole", is_flag=True, help="Allow an audio source that is not named BlackHole.")
@click.option("--focus/--no-focus", "focus_before_record", default=True, show_default=True, help="Bring the Douyin browser window to the front before recording.")
@click.pass_context
def record(
    ctx: click.Context,
    output: Path,
    duration: float,
    video_index: int,
    audio_index: int,
    fps: int,
    scale_width: int | None,
    verify: bool,
    dry_run: bool,
    allow_non_blackhole: bool,
    focus_before_record: bool,
) -> None:
    """Record screen video plus AVFoundation audio into an MP4."""
    focus_result = None
    if focus_before_record:
        focus_result = actions.focus(home=ctx.obj["home"])
    try:
        result = record_avfoundation(
            output=output,
            duration=duration,
            video_index=video_index,
            audio_index=audio_index,
            fps=fps,
            scale_width=scale_width,
            allow_non_blackhole=allow_non_blackhole,
            verify=verify,
            dry_run=dry_run,
        )
        if focus_result is not None:
            result.data["focus"] = focus_result.to_dict()
    except Exception as exc:
        result = ActionResult(False, "record", str(exc))
        if focus_result is not None:
            result.data["focus"] = focus_result.to_dict()
    emit(ctx, result)


def repl(ctx: click.Context) -> None:
    click.echo("Douyin web CLI REPL. Type `help` for commands, `exit` to quit.")
    while True:
        try:
            line = input("douyin> ")
        except (EOFError, KeyboardInterrupt):
            click.echo()
            return
        line = line.strip()
        if not line:
            continue
        if line in {"exit", "quit", ":q"}:
            return
        if line in {"help", "?"}:
            click.echo(ctx.get_help())
            continue
        args = shlex.split(line)
        try:
            cli.main(
                args=args,
                prog_name="douyin-web",
                standalone_mode=False,
                obj={
                    "json_output": ctx.obj.get("json_output", False),
                    "home": ctx.obj.get("home"),
                    "auto_screenshot": ctx.obj.get("auto_screenshot", True),
                    "screenshot_dir": ctx.obj.get("screenshot_dir"),
                },
            )
        except SystemExit:
            pass
        except Exception as exc:
            click.echo(f"error: {exc}", err=True)


def emit(ctx: click.Context, result: ActionResult) -> None:
    _attach_auto_screenshot(ctx, result)
    append_history(result, home=ctx.obj.get("home"))
    if ctx.obj.get("json_output"):
        click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        prefix = "OK" if result.ok else "ERR"
        click.echo(f"{prefix} {result.action}: {result.message}")
        if result.data:
            click.echo(json.dumps(_compact_data(result.data), ensure_ascii=False, indent=2))
    if not result.ok:
        sys.exit(1)


def _attach_auto_screenshot(ctx: click.Context, result: ActionResult) -> None:
    if not ctx.obj.get("auto_screenshot", True):
        return
    if result.action in {"close", "devices", "record", "screenshot", "state"}:
        return
    output = _auto_screenshot_path(ctx, result.action)
    shot = actions.screenshot(output=output, home=ctx.obj.get("home"))
    payload = {
        "ok": shot.ok,
        "path": str(output),
        "message": shot.message,
    }
    if shot.data.get("url"):
        payload["url"] = shot.data["url"]
    result.data.setdefault("screenshot", payload)


def _auto_screenshot_path(ctx: click.Context, action: str) -> Path:
    root = ctx.obj.get("screenshot_dir")
    if root is None:
        root = home_dir(ctx.obj.get("home")) / "screenshots"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return Path(root).expanduser() / f"{timestamp}-{action}.png"


def _compact_data(data):
    if "raw" in data and isinstance(data["raw"], str) and len(data["raw"]) > 2000:
        data = dict(data)
        data["raw"] = data["raw"][:2000] + "\n... truncated ..."
    return data

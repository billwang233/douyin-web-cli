from pathlib import Path

from click.testing import CliRunner

from cli_anything.douyin_web.core.config import DEFAULT_HOME, feed_url, profile_home_dir, resolve_home
from cli_anything.douyin_web.core.state import SessionState, load_session, save_session
from cli_anything.douyin_web.douyin_web_cli import cli
from cli_anything.douyin_web.utils.browser_backend import infer_login_status
from cli_anything.douyin_web.utils.recording import parse_avfoundation_devices


def test_feed_url_mapping():
    assert feed_url("recommend").endswith("?recommend=1")
    assert feed_url("jingxuan").endswith("/jingxuan")
    assert feed_url("ai-search").endswith("/aisearch")
    assert feed_url("friends").endswith("/friend")
    assert feed_url("mine").endswith("/user/self")
    assert feed_url("series").endswith("/series")
    assert feed_url("https://www.douyin.com/user/example") == "https://www.douyin.com/user/example"


def test_session_roundtrip(tmp_path: Path):
    state = SessionState(endpoint="http://127.0.0.1:9223", port=9223, pid=123)
    save_session(state, tmp_path)
    loaded = load_session(tmp_path)
    assert loaded.endpoint == state.endpoint
    assert loaded.port == 9223
    assert loaded.pid == 123


def test_profile_home_mapping():
    assert profile_home_dir("project-a") == DEFAULT_HOME / "profiles" / "project-a"
    assert resolve_home(None, "project.a_1") == DEFAULT_HOME / "profiles" / "project.a_1"


def test_profile_rejects_unsafe_names():
    for value in ["../x", "/tmp/x", "", "-bad", "bad/name"]:
        try:
            profile_home_dir(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected unsafe profile to fail: {value}")


def test_parse_avfoundation_devices():
    output = """
    [AVFoundation indev @ 0x123] AVFoundation video devices:
    [AVFoundation indev @ 0x123] [0] FaceTime HD Camera
    [AVFoundation indev @ 0x123] [2] Capture screen 1
    [AVFoundation indev @ 0x123] AVFoundation audio devices:
    [AVFoundation indev @ 0x123] [0] BlackHole 2ch
    [AVFoundation indev @ 0x123] [1] MacBook Pro Microphone
    """
    devices = parse_avfoundation_devices(output)
    assert devices["video"][1]["name"] == "Capture screen 1"
    assert devices["audio"][0]["name"] == "BlackHole 2ch"


def test_cli_state_json(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--home", str(tmp_path), "state"])
    assert result.exit_code == 0
    assert '"action": "state"' in result.output
    assert '"endpoint_ready": false' in result.output


def test_cli_profile_state_json():
    runner = CliRunner()
    result = runner.invoke(cli, ["--json", "--profile", "pytest-profile", "state"])
    assert result.exit_code == 0
    assert '"action": "state"' in result.output


def test_cli_rejects_home_and_profile(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--home", str(tmp_path), "--profile", "x", "state"])
    assert result.exit_code == 1
    assert "use either --home or --profile" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Control Douyin web" in result.output
    assert "prepare" in result.output
    assert "sound" in result.output
    assert "dismiss" in result.output
    assert "focus" in result.output
    assert "--profile" in result.output
    assert "info" in result.output
    assert "search" in result.output
    assert "seek" in result.output
    assert "rate" in result.output
    assert "volume" in result.output
    assert "comments" in result.output
    assert "danmaku-send" in result.output
    assert "follow-author" in result.output
    assert "loop" in result.output
    assert "press" in result.output
    assert "click-text" in result.output
    assert "--no-screenshot" in result.output

    record_help = runner.invoke(cli, ["record", "--help"])
    assert record_help.exit_code == 0
    assert "--no-focus" in record_help.output


def test_page_control_requires_session(tmp_path: Path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--home", str(tmp_path), "current"])
    assert result.exit_code == 1
    assert "no active browser session" in result.output


def test_login_prompt_is_not_logged_in():
    body_text = "登录后免费畅享高清视频 扫码登录 验证码登录 私信 我的 通知"
    status, markers = infer_login_status(body_text, {"passport_csrf_token", "passport_auth_status"})
    assert status == "logged_out"
    assert markers["login_text"] is True
    assert markers["cookie_login"] is False

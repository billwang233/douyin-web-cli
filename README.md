# Douyin Web CLI

This project owns only the Douyin web control layer. Keep browsing strategy, persona behavior, recommendation guidance, and video creation ideas outside this browser automation layer.

## Scope

In scope:

- Launch or reuse a controllable Chrome/Chromium browser session.
- Open Douyin feeds and URLs.
- Check login state and wait while the user logs in manually.
- Control playback, sound, fullscreen, clean-screen, danmaku, and feed navigation.
- Like, favorite, share, and draft or submit comments.
- Capture screenshots and record screen video plus system audio.
- Package those actions as a CLI-Anything style harness.

Out of scope:

- Deciding which videos to watch.
- Taste modeling, persona simulation, or browsing policy.
- Video creation ideas, scripts, prompts, publishing plans, or content strategy.

## Install

Install from GitHub:

```bash
python3 -m pip install "git+https://github.com/billwang233/douyin-web-cli.git"
python3 -m playwright install chromium
douyin-web --help
```

Install from a local checkout for development:

```bash
export DOUYIN_CLI_ROOT=/path/to/douyin-cli
cd "$DOUYIN_CLI_ROOT"
python3 -m pip install -e .
python3 -m playwright install chromium
```

If the installed command is not on `PATH`, use the local wrapper:

```bash
"$DOUYIN_CLI_ROOT/bin/douyin-web" --help
```

## Agent Skill

This repository also includes a portable Agent skill:

```text
skills/douyin-web-control/
```

The skill explains when an Agent should use `douyin-web`, how to call the CLI, which actions affect the account, and where to find the feature matrix. It is kept in a generic `skills/` directory instead of a platform-specific hidden directory, so Agent runtimes can copy or install it according to their own conventions.

## Command Surface

```bash
douyin-web launch
douyin-web open recommend
douyin-web feed jingxuan
douyin-web status
douyin-web wait-login --timeout 300
douyin-web current
douyin-web reload
douyin-web dismiss
douyin-web click-text "我知道了"
douyin-web press Escape
douyin-web info
douyin-web search "新进职员姜会长"
douyin-web play pause
douyin-web play resume
douyin-web sound on
douyin-web seek --percent 30
douyin-web rate 1.25
douyin-web volume 0.8
douyin-web next
douyin-web prev
douyin-web clean
douyin-web danmaku off
douyin-web danmaku-send "前方高能" --no-submit
douyin-web loop
douyin-web fullscreen
douyin-web prepare
douyin-web focus
douyin-web like
douyin-web favorite
douyin-web share
douyin-web comments open
douyin-web comment "这条很有意思" --no-submit
douyin-web screenshot recordings/current.png
douyin-web devices
douyin-web record recordings/sample.mp4 --duration 15 --video-index VIDEO_INDEX --audio-index BLACKHOLE_AUDIO_INDEX --verify
```

Use `--json` before the command for machine-readable output:

```bash
douyin-web --json current
```

Page actions capture a viewport screenshot by default. The screenshot path is included in JSON output under `data.screenshot.path`.

```bash
douyin-web --json like
douyin-web --no-screenshot --json like
douyin-web --screenshot-dir /tmp/douyin-shots --json next
```

## Recording Boundary

`douyin-web record` uses AVFoundation through `ffmpeg`. It refuses non-BlackHole audio by default because Douyin playback should capture system audio, not the microphone. Run `douyin-web devices` before each recording session because AVFoundation indexes can change.

`record` brings Chrome and the current Douyin tab to the front by default before starting `ffmpeg`. Use `--no-focus` only when you have already arranged the capture display yourself.

## Test

```bash
cd "$DOUYIN_CLI_ROOT"
python3 -m pytest
"$DOUYIN_CLI_ROOT/bin/douyin-web" --json state
```

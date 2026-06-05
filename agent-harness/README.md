# Douyin Web CLI

A CLI-Anything style harness for controlling the Douyin web experience from the terminal.

This repository intentionally focuses on the control layer. It does not include video-watching strategy or video-creation ideation.

## Install

```bash
export DOUYIN_CLI_ROOT=/path/to/douyin-cli
cd "$DOUYIN_CLI_ROOT/agent-harness"
python3 -m pip install -e .
```

If Playwright has not installed a browser runtime yet:

```bash
python3 -m playwright install chromium
```

The CLI prefers a local Chrome/Chromium executable for persistent browser control over CDP. You can override it:

```bash
export DOUYIN_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

If your Python scripts directory is not on `PATH`, use the repository-local wrapper:

```bash
"$DOUYIN_CLI_ROOT/bin/douyin-web" --help
```

## Quick Start

Launch a controllable browser:

```bash
douyin-web launch
```

Open the recommendation feed:

```bash
douyin-web open recommend
```

Check login state:

```bash
douyin-web status
```

Wait for manual login:

```bash
douyin-web wait-login --timeout 300
```

Prepare a cleaner fullscreen playback state:

```bash
douyin-web sound on
douyin-web clean
douyin-web danmaku off
douyin-web fullscreen
douyin-web prepare
```

Control playback:

```bash
douyin-web play pause
douyin-web play resume
douyin-web play toggle
douyin-web --json play state
douyin-web seek --seconds 30
douyin-web rate 1.25
douyin-web volume 0.8
douyin-web next
douyin-web prev
```

Engagement actions:

```bash
douyin-web like
douyin-web follow-author
douyin-web favorite
douyin-web share
douyin-web comments open
douyin-web comment "这条很有意思" --no-submit
douyin-web danmaku-send "前方高能" --no-submit
```

Screenshots:

```bash
douyin-web screenshot recordings/current.png
```

Inspect current page and video state:

```bash
douyin-web current
douyin-web info
douyin-web search "新进职员姜会长"
douyin-web focus
douyin-web reload
douyin-web dismiss
douyin-web click-text "我知道了"
douyin-web press Escape
```

List AVFoundation devices:

```bash
douyin-web devices
```

Record with display capture and BlackHole audio:

```bash
douyin-web record recordings/sample.mp4 --duration 15 --video-index 2 --audio-index 0
```

The recording command brings Chrome and the current Douyin tab to the front by default. It refuses to continue unless the selected audio device looks like `BlackHole`, unless you explicitly pass `--allow-non-blackhole`.

## JSON Output

Put `--json` before the command:

```bash
douyin-web --json status
```

Page actions capture a viewport screenshot by default and include it in JSON output:

```bash
douyin-web --json like
douyin-web --no-screenshot --json like
douyin-web --screenshot-dir /tmp/douyin-shots --json next
```

## REPL

Run with no subcommand:

```bash
douyin-web
```

Then type commands such as:

```text
open recommend
status
--json play state
exit
```

## State

The browser session state is stored under:

```text
~/.douyin-web-cli/
```

Override it with:

```bash
export DOUYIN_WEB_HOME=/path/to/state
```

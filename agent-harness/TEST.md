# Test Plan

## Local Unit Tests

Run from the harness root:

```bash
export DOUYIN_CLI_ROOT=/path/to/douyin-cli
cd "$DOUYIN_CLI_ROOT/agent-harness"
python3 -m pytest
```

These tests cover state persistence, feed URL mapping, AVFoundation device parsing, and CLI command behavior that does not need a live browser.

## Install Smoke Test

```bash
cd "$DOUYIN_CLI_ROOT/agent-harness"
python3 -m pip install -e .
douyin-web --help
douyin-web --json state
```

Expected result: both commands exit successfully, and `state` emits machine-readable JSON.

Repository-local wrapper smoke test:

```bash
"$DOUYIN_CLI_ROOT/bin/douyin-web" --help
"$DOUYIN_CLI_ROOT/bin/douyin-web" --json state
```

## Manual Browser E2E

```bash
douyin-web launch
douyin-web open recommend
douyin-web wait-login --timeout 300
douyin-web status
douyin-web --json play state
douyin-web screenshot recordings/manual-smoke.png
```

Expected result: a Chrome/Chromium window opens Douyin, the login check returns either `logged_in`, `logged_out`, or `unknown`, and the screenshot file is created.

## Optional Recording E2E

List devices first:

```bash
douyin-web devices
```

Then record using the display and `BlackHole 2ch` audio indexes:

```bash
douyin-web record recordings/manual-15s.mp4 --duration 15 --video-index VIDEO_INDEX --audio-index BLACKHOLE_AUDIO_INDEX --verify
```

Expected result: the command refuses microphone-like audio devices, writes an MP4 when `BlackHole` is selected, and prints ffprobe/volumedetect verification.

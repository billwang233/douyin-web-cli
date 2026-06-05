# cli_anything.douyin_web

Python package for the Douyin web CLI harness.

Primary entry point:

```bash
douyin-web
```

The browser backend launches Chrome/Chromium with a local CDP endpoint, stores the session under `~/.douyin-web-cli`, and lets later CLI invocations reconnect to the same visible browser window.

The package is intentionally scoped to control actions only. Do not add persona strategy, browsing recommendations, or video-creation logic here.

Core commands:

```bash
douyin-web launch
douyin-web open recommend
douyin-web feed jingxuan
douyin-web status
douyin-web wait-login --timeout 300
douyin-web current
douyin-web info
douyin-web search "KEYWORD"
douyin-web reload
douyin-web play state
douyin-web sound on
douyin-web seek --percent 30
douyin-web rate 1.25
douyin-web volume 0.8
douyin-web next
douyin-web prev
douyin-web prepare
douyin-web focus
douyin-web loop
douyin-web like
douyin-web favorite
douyin-web share
douyin-web comments open
douyin-web comment "TEXT" --no-submit
douyin-web danmaku-send "TEXT" --no-submit
douyin-web press Escape
douyin-web screenshot recordings/current.png
douyin-web record recordings/sample.mp4 --duration 15 --video-index VIDEO_INDEX --audio-index BLACKHOLE_AUDIO_INDEX --verify
```

Page actions capture a viewport screenshot by default. Use `--no-screenshot` to disable this or `--screenshot-dir DIR` to choose where automatic screenshots are written.

`record` focuses Chrome and the current Douyin tab before starting capture by default. Use `--no-focus` to disable that behavior.

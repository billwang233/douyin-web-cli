# Douyin Web Control Harness

This project is the CLI boundary for Douyin web control only.

It owns:

- Opening Douyin web pages.
- Launching or reusing a controllable browser session.
- Checking and waiting for login state.
- Navigating Douyin web feeds such as `recommend` and `jingxuan`.
- Player actions such as fullscreen, clean screen, danmaku, pause, resume, and mute prompts.
- Page and feed navigation such as current state, reload, next video, and previous video.
- Engagement actions such as like, favorite, share, and comment drafting/submitting.
- Screenshots and AVFoundation-based recording.

It does not own:

- Guidance about which videos to watch next.
- Persona, browsing strategy, recommendation policy, or taste modeling.
- Video creation ideas, scripts, prompts, or publishing strategy.

## Shape

The harness follows the CLI-Anything convention:

```text
agent-harness/
├── setup.py
└── cli_anything/
    └── douyin_web/
        ├── douyin_web_cli.py
        ├── core/
        ├── utils/
        └── tests/
```

The installed command is:

```bash
douyin-web
```

The long CLI-Anything style alias is:

```bash
cli-anything-douyin-web
```

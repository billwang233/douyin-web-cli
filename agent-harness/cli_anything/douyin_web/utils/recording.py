from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import re
import shlex
import subprocess

from ..core.state import ActionResult


DEVICE_RE = re.compile(r"\[(?P<index>\d+)\]\s+(?P<name>.+)$")


def list_avfoundation_devices(ffmpeg: str = "ffmpeg") -> ActionResult:
    command = [ffmpeg, "-f", "avfoundation", "-list_devices", "true", "-i", ""]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)  # noqa: S603
    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    devices = parse_avfoundation_devices(output)
    return ActionResult(
        ok=bool(output),
        action="devices",
        message="listed AVFoundation devices" if output else "ffmpeg produced no device output",
        data={"devices": devices, "raw": output, "returncode": completed.returncode},
    )


def parse_avfoundation_devices(output: str) -> dict[str, list[dict[str, Any]]]:
    current = None
    devices = {"video": [], "audio": []}
    for line in output.splitlines():
        if "AVFoundation video devices" in line:
            current = "video"
            continue
        if "AVFoundation audio devices" in line:
            current = "audio"
            continue
        if current is None:
            continue
        match = DEVICE_RE.search(line.strip())
        if match:
            devices[current].append(
                {
                    "index": int(match.group("index")),
                    "name": match.group("name").strip(),
                }
            )
    return devices


def assert_blackhole_audio(audio_index: int, allow_non_blackhole: bool = False, ffmpeg: str = "ffmpeg") -> Optional[str]:
    result = list_avfoundation_devices(ffmpeg=ffmpeg)
    audio_devices = result.data.get("devices", {}).get("audio", [])
    selected = next((device for device in audio_devices if device["index"] == audio_index), None)
    if not selected:
        raise RuntimeError(f"audio device index {audio_index} was not found; run `douyin-web devices`")
    name = selected["name"]
    if "blackhole" not in name.lower() and not allow_non_blackhole:
        raise RuntimeError(
            f"refusing to record audio device [{audio_index}] {name!r}; expected BlackHole. "
            "Pass --allow-non-blackhole only when you intentionally want another source."
        )
    return name


def record_avfoundation(
    output: Path,
    duration: float,
    video_index: int,
    audio_index: int,
    fps: int = 30,
    scale_width: Optional[int] = None,
    allow_non_blackhole: bool = False,
    verify: bool = False,
    dry_run: bool = False,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> ActionResult:
    audio_name = assert_blackhole_audio(audio_index, allow_non_blackhole=allow_non_blackhole, ffmpeg=ffmpeg)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-f",
        "avfoundation",
        "-capture_cursor",
        "0",
        "-framerate",
        str(fps),
        "-i",
        f"{video_index}:{audio_index}",
        "-t",
        str(duration),
    ]
    filters = [f"fps={fps}"]
    if scale_width:
        filters.insert(0, f"scale={scale_width}:-2")
    command.extend(
        [
            "-vf",
            ",".join(filters),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output),
        ]
    )
    if dry_run:
        return ActionResult(
            ok=True,
            action="record",
            message="dry run only",
            data={"command": shell_join(command), "audio_device": audio_name},
        )

    completed = subprocess.run(command, text=True, capture_output=True, check=False)  # noqa: S603
    ok = completed.returncode == 0 and output.exists()
    data: dict[str, Any] = {
        "path": str(output),
        "command": shell_join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "audio_device": audio_name,
    }
    if ok and verify:
        data["verification"] = verify_recording(output, ffmpeg=ffmpeg, ffprobe=ffprobe)
    return ActionResult(
        ok=ok,
        action="record",
        message="recorded MP4" if ok else "recording failed",
        data=data,
    )


def verify_recording(output: Path, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> dict[str, Any]:
    probe_cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,avg_frame_rate,width,height",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(output),
    ]
    volume_cmd = [
        ffmpeg,
        "-i",
        str(output),
        "-af",
        "volumedetect",
        "-vn",
        "-f",
        "null",
        "-",
    ]
    probe = subprocess.run(probe_cmd, text=True, capture_output=True, check=False)  # noqa: S603
    volume = subprocess.run(volume_cmd, text=True, capture_output=True, check=False)  # noqa: S603
    return {
        "ffprobe": {
            "command": shell_join(probe_cmd),
            "returncode": probe.returncode,
            "stdout": probe.stdout,
            "stderr": probe.stderr,
        },
        "volumedetect": {
            "command": shell_join(volume_cmd),
            "returncode": volume.returncode,
            "stdout": volume.stdout,
            "stderr": volume.stderr,
        },
    }


def shell_join(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)

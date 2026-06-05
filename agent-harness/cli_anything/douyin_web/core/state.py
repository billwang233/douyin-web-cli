from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional
import json
import time

from .config import history_path, session_path


@dataclass
class ActionResult:
    ok: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class SessionState:
    endpoint: Optional[str] = None
    port: Optional[int] = None
    pid: Optional[int] = None
    browser_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    active_url: Optional[str] = None
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def empty(cls) -> "SessionState":
        return cls()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionState":
        valid = {key for key in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in payload.items() if key in valid})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def has_endpoint(self) -> bool:
        return bool(self.endpoint)


def load_session(home: Optional[str | Path] = None) -> SessionState:
    path = session_path(home)
    if not path.exists():
        return SessionState.empty()
    with path.open("r", encoding="utf-8") as handle:
        return SessionState.from_dict(json.load(handle))


def save_session(state: SessionState, home: Optional[str | Path] = None) -> None:
    path = session_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.updated_at = time.time()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state.to_dict(), handle, ensure_ascii=False, indent=2)


def clear_session(home: Optional[str | Path] = None) -> None:
    path = session_path(home)
    if path.exists():
        path.unlink()


def append_history(result: ActionResult, home: Optional[str | Path] = None) -> None:
    path = history_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "time": time.time(),
        **result.to_dict(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

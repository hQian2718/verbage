from __future__ import annotations

import os
from dataclasses import dataclass


def get_optional_int_env(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a Discord id integer.") from exc


@dataclass(frozen=True)
class GameConfig:
    delay_per_char: float
    min_delay: float
    max_delay: float
    typing_delay: float
    wait_scale: float
    cleanup_prompt_timeout: float
    default_channel: str = "Game"

    @classmethod
    def from_env(cls) -> "GameConfig":
        return cls(
            delay_per_char=float(os.getenv("DIALOG_DELAY_PER_CHAR", "0.03")),
            min_delay=float(os.getenv("DIALOG_MIN_DELAY", "1.5")),
            max_delay=float(os.getenv("DIALOG_MAX_DELAY", "6")),
            typing_delay=float(os.getenv("DIALOG_TYPING_DELAY", "0.5")),
            wait_scale=float(os.getenv("DIALOG_WAIT_SCALE", "1")),
            cleanup_prompt_timeout=float(os.getenv("DIALOG_CLEANUP_TIMEOUT", "120")),
            default_channel=os.getenv("GAME_DEFAULT_CHANNEL", "Game").strip() or "Game",
        )

    def reading_delay_for(self, text: str) -> float:
        return min(self.max_delay, max(self.min_delay, len(text) * self.delay_per_char))

    def dialogue_seconds(self, text: str) -> float:
        return self.typing_delay + self.reading_delay_for(text)

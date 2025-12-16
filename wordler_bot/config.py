import os
from dataclasses import dataclass
from datetime import time, timezone
from pathlib import Path

from dotenv import load_dotenv


class SettingsError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(frozen=True)
class BotSettings:
    token: str
    wordle_channel_id: int
    data_path: Path
    command_prefix: str = "!"
    leaderboard_size: int = 10
    leaderboard_post_time: time | None = None
    leaderboard_post_channel_id: int | None = None

    @classmethod
    def from_env(cls) -> "BotSettings":
        load_dotenv()

        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise SettingsError("Missing DISCORD_TOKEN")

        channel_raw = os.getenv("WORDLE_CHANNEL_ID")
        if not channel_raw:
            raise SettingsError("Missing WORDLE_CHANNEL_ID")

        try:
            channel_id = int(channel_raw)
        except ValueError as exc:
            raise SettingsError("WORDLE_CHANNEL_ID must be an integer") from exc

        data_path = Path(os.getenv("DATA_PATH", "./data/wordle_stats.json")).expanduser()
        try:
            leaderboard_size = int(os.getenv("LEADERBOARD_SIZE", "10"))
        except ValueError as exc:
            raise SettingsError("LEADERBOARD_SIZE must be an integer") from exc

        post_time_raw = os.getenv("LEADERBOARD_POST_TIME")
        post_time: time | None = None
        if post_time_raw:
            try:
                hour_str, minute_str = post_time_raw.split(":", 1)
                post_time = time(hour=int(hour_str), minute=int(minute_str), tzinfo=timezone.utc)
            except ValueError as exc:
                raise SettingsError("LEADERBOARD_POST_TIME must be HH:MM (24h)") from exc

        post_channel_raw = os.getenv("LEADERBOARD_POST_CHANNEL_ID")
        if post_channel_raw:
            try:
                post_channel_id = int(post_channel_raw)
            except ValueError as exc:
                raise SettingsError("LEADERBOARD_POST_CHANNEL_ID must be an integer") from exc
        else:
            post_channel_id = channel_id

        return cls(
            token=token.strip(),
            wordle_channel_id=channel_id,
            data_path=data_path,
            command_prefix=os.getenv("COMMAND_PREFIX", "!").strip() or "!",
            leaderboard_size=leaderboard_size,
            leaderboard_post_time=post_time,
            leaderboard_post_channel_id=post_channel_id,
        )

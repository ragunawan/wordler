import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .parser import WordleResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserSummary:
    user_id: str
    display_name: str
    games_played: int
    wins: int
    losses: int
    win_rate: float
    average_attempts: Optional[float]
    guess_distribution: Dict[str, int]
    total_attempts: int
    last_puzzle: Optional[int]


class StatsManager:
    """In-memory statistics store persisted to disk."""

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self._stats: Dict[str, Dict] = {}
        self._processed_messages: set[str] = set()
        self._lock = asyncio.Lock()

    def load(self) -> None:
        """Load stats from disk."""
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            logger.info("No stats file found at %s, starting fresh", self.data_path)
            self._stats = {}
            self._processed_messages = set()
            return

        try:
            with self.data_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
                if not isinstance(payload, dict):
                    logger.warning("Stats file %s malformed, resetting", self.data_path)
                    self._stats = {}
                    self._processed_messages = set()
                    return
                users = payload.get("users")
                if isinstance(users, dict):
                    self._stats = users
                    logger.info("Loaded %s Wordle players from %s", len(users), self.data_path)
                else:
                    logger.warning("Stats file %s missing 'users' object, resetting", self.data_path)
                    self._stats = {}
                processed = payload.get("processed_messages")
                if isinstance(processed, list):
                    self._processed_messages = {str(item) for item in processed}
                else:
                    self._processed_messages = set()
        except json.JSONDecodeError:
            logger.exception("Failed to parse stats file %s, resetting store", self.data_path)
            self._stats = {}
            self._processed_messages = set()

    async def record_result(
        self,
        user,
        result: WordleResult,
        *,
        message_id: int | None = None,
        message_key: str | None = None,
    ) -> bool:
        """Persist a parsed Wordle result for a Discord user."""
        async with self._lock:
            key: Optional[str] = message_key
            if key is None and message_id is not None:
                key = str(message_id)
            if key and key in self._processed_messages:
                logger.debug("Skipping already recorded entry %s", key)
                return False
            stats = self._stats.setdefault(str(user.id), self._blank_stats(user.display_name))
            stats["display_name"] = user.display_name

            if result.success:
                stats["wins"] += 1
                stats["total_attempts"] += result.attempts or 0
                bucket = str(result.attempts or 0)
                if bucket not in stats["guess_distribution"]:
                    stats["guess_distribution"][bucket] = 0
                stats["guess_distribution"][bucket] += 1
            else:
                stats["losses"] += 1

            stats["games_played"] = stats["wins"] + stats["losses"]
            stats["last_puzzle"] = result.puzzle_number
            stats["last_result"] = {
                "puzzle_number": result.puzzle_number,
                "success": result.success,
                "attempts": result.attempts,
                "hard_mode": result.hard_mode,
                "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
            }

            logger.info(
                "Recording Wordle %s for %s (success=%s attempts=%s)",
                result.puzzle_number,
                user.display_name,
                result.success,
                result.attempts,
            )

            if key:
                self._processed_messages.add(key)

            self._persist_locked()
            return True

    def get_user_summary(self, user_id: int) -> Optional[UserSummary]:
        stats = self._stats.get(str(user_id))
        if not stats:
            return None
        return self._make_summary(str(user_id), stats)

    def leaderboard(self, limit: int = 10) -> List[UserSummary]:
        entries: List[UserSummary] = []
        for user_id, stats in self._stats.items():
            summary = self._make_summary(user_id, stats)
            if summary.games_played == 0:
                continue
            entries.append(summary)

        entries.sort(
            key=lambda item: (
                -item.win_rate,
                item.average_attempts if item.average_attempts is not None else 99,
                -item.wins,
                item.display_name.lower(),
            )
        )
        return entries[:limit]

    def _make_summary(self, user_id: str, stats: Dict) -> UserSummary:
        games_played = stats.get("games_played", 0)
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total_attempts = stats.get("total_attempts", 0)
        win_rate = (wins / games_played) if games_played else 0.0
        average_attempts = (total_attempts / wins) if wins else None
        distribution = stats.get("guess_distribution") or {}
        strings = {str(i): distribution.get(str(i), 0) for i in range(1, 7)}
        return UserSummary(
            user_id=user_id,
            display_name=stats.get("display_name", "Unknown Player"),
            games_played=games_played,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            average_attempts=average_attempts,
            guess_distribution=strings,
            total_attempts=total_attempts,
            last_puzzle=stats.get("last_puzzle"),
        )

    def _persist_locked(self) -> None:
        payload = {
            "users": self._stats,
            "processed_messages": sorted(self._processed_messages),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        tmp_path = self.data_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        tmp_path.replace(self.data_path)

    @staticmethod
    def _blank_stats(display_name: str) -> Dict:
        return {
            "display_name": display_name,
            "games_played": 0,
            "wins": 0,
            "losses": 0,
            "total_attempts": 0,
            "guess_distribution": {str(i): 0 for i in range(1, 7)},
            "last_puzzle": None,
            "last_result": None,
        }

import pytest

pytest.importorskip("discord")

from wordler_bot.bot import build_leaderboard_embed
from wordler_bot.stats import UserSummary


def make_summary(user_id: str, name: str, average_attempts: float, wins: int, win_rate: float) -> UserSummary:
    return UserSummary(
        user_id=user_id,
        display_name=name,
        games_played=wins,
        wins=wins,
        losses=0,
        win_rate=win_rate,
        average_attempts=average_attempts,
        guess_distribution={str(i): 0 for i in range(1, 7)},
        total_attempts=int(average_attempts * wins),
        last_puzzle=None,
    )


def test_embed_shows_rank_movement_indicators():
    entries = [
        make_summary("1", "Alice", 3.0, wins=5, win_rate=0.9),
        make_summary("2", "Bob", 4.0, wins=5, win_rate=0.8),
    ]
    previous_ranks = {"1": 2, "2": 1}

    embed = build_leaderboard_embed(entries, previous_ranks)

    assert "⬆️ 1." in embed.description
    assert "⬇️ 2." in embed.description

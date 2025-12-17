import asyncio

import pytest

from wordler_bot.stats import StatsManager


def make_player(display_name: str, *, games: int, wins: int, losses: int, total_attempts: int):
    return {
        "display_name": display_name,
        "games_played": games,
        "wins": wins,
        "losses": losses,
        "total_attempts": total_attempts,
        "guess_distribution": {str(i): 0 for i in range(1, 7)},
        "last_puzzle": None,
        "last_result": None,
    }


@pytest.fixture
def stats_manager(tmp_path):
    return StatsManager(tmp_path / "stats.json")


def test_leaderboard_prioritizes_average_attempts(stats_manager):
    stats_manager._stats = {
        "1": make_player("Efficient", games=10, wins=5, losses=5, total_attempts=15),
        "2": make_player("Less Efficient", games=10, wins=5, losses=5, total_attempts=25),
    }

    leaderboard = stats_manager.leaderboard()

    assert leaderboard[0].display_name == "Efficient"
    assert leaderboard[1].display_name == "Less Efficient"


def test_leaderboard_breaks_average_ties_with_wins(stats_manager):
    stats_manager._stats = {
        "1": make_player("More Wins", games=10, wins=6, losses=4, total_attempts=18),
        "2": make_player("Fewer Wins", games=8, wins=3, losses=5, total_attempts=9),
    }

    leaderboard = stats_manager.leaderboard()

    assert leaderboard[0].display_name == "More Wins"
    assert leaderboard[1].display_name == "Fewer Wins"


def test_leaderboard_breaks_win_ties_with_win_rate(stats_manager):
    stats_manager._stats = {
        "1": make_player("Higher Win Rate", games=6, wins=6, losses=0, total_attempts=18),
        "2": make_player("Lower Win Rate", games=12, wins=6, losses=6, total_attempts=18),
    }

    leaderboard = stats_manager.leaderboard()

    assert leaderboard[0].display_name == "Higher Win Rate"
    assert leaderboard[1].display_name == "Lower Win Rate"


def test_leaderboard_breaks_full_ties_with_name(stats_manager):
    stats_manager._stats = {
        "1": make_player("Alpha", games=10, wins=5, losses=5, total_attempts=15),
        "2": make_player("Beta", games=10, wins=5, losses=5, total_attempts=15),
    }

    leaderboard = stats_manager.leaderboard()

    assert [entry.display_name for entry in leaderboard] == ["Alpha", "Beta"]


def test_leaderboard_snapshot_round_trip(stats_manager):
    snapshot = ["1", "3", "2"]
    asyncio.run(stats_manager.update_leaderboard_snapshot(snapshot))

    assert stats_manager.get_leaderboard_snapshot() == snapshot

import re
from dataclasses import dataclass
from typing import List, Optional

WORDLE_REGEX = re.compile(
    r"^Wordle\s+(?P<puzzle>\d+)\s+(?P<score>[0-6Xx])/6(?P<hard>\*?)",
    re.MULTILINE,
)
SUMMARY_LINE_REGEX = re.compile(r"(?P<score>[0-6Xx])/6:\s*(?P<body>.+)")
MENTION_REGEX = re.compile(r"<@!?(?P<id>\d+)>")
PLAIN_HANDLE_REGEX = re.compile(r"@(?P<handle>[A-Za-z0-9_.-]+)")


@dataclass(frozen=True)
class WordleResult:
    """Structured representation of a single Wordle share message."""

    puzzle_number: Optional[int]
    success: bool
    attempts: Optional[int]
    hard_mode: bool
    board: List[str]


@dataclass(frozen=True)
class DailySummaryEntry:
    """Represents a parsed entry from the Wordle group summary message."""

    user_id: Optional[int]
    handle: Optional[str]
    success: bool
    attempts: Optional[int]


def parse_wordle_message(content: str) -> Optional[WordleResult]:
    """Return a WordleResult if the Discord message contains a share code."""

    if not content:
        return None

    match = WORDLE_REGEX.search(content)
    if not match:
        return None

    puzzle_number = int(match.group("puzzle"))
    score_raw = match.group("score").upper()
    hard_mode = bool(match.group("hard"))
    success = score_raw != "X"
    attempts = int(score_raw) if success else None

    board_lines: List[str] = []
    for line in content.splitlines()[1:]:
        striped = line.strip()
        if not striped:
            continue
        board_lines.append(line.rstrip())

    return WordleResult(
        puzzle_number=puzzle_number,
        success=success,
        attempts=attempts,
        hard_mode=hard_mode,
        board=board_lines[:6],  # Wordle boards have at most six rows
    )


def parse_daily_summary(content: str) -> List[DailySummaryEntry]:
    """
    Parse the official Wordle daily summary message.

    These summaries list each player grouped by number of attempts, e.g.
    '5/6: <@123> <@456>'. We extract the mention IDs so the bot can look up
    the referenced members later.
    """

    if not content:
        return []

    entries: List[DailySummaryEntry] = []
    seen: set[str] = set()
    for line in content.splitlines():
        match = SUMMARY_LINE_REGEX.search(line)
        if not match:
            continue
        score = match.group("score").upper()
        body = match.group("body").strip()
        mention_ids = MENTION_REGEX.findall(body)
        success = score != "X"
        attempts = int(score) if success else None
        added = False
        for raw_id in mention_ids:
            user_id = int(raw_id)
            key = f"id:{user_id}"
            if key in seen:
                continue
            seen.add(key)
            entries.append(DailySummaryEntry(user_id=user_id, handle=None, success=success, attempts=attempts))
            added = True

        stripped_body = MENTION_REGEX.sub(" ", body)
        for match_handle in PLAIN_HANDLE_REGEX.finditer(stripped_body):
            handle = match_handle.group("handle").strip()
            if not handle:
                continue
            key = f"handle:{handle.lower()}"
            if key in seen:
                continue
            seen.add(key)
            entries.append(DailySummaryEntry(user_id=None, handle=handle, success=success, attempts=attempts))
            added = True

        if not added:
            continue
    return entries

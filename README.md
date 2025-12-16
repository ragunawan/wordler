## Wordler Discord Bot

Python Discord bot that listens to a dedicated Wordle results channel, parses the shared messages, and maintains rolling statistics + a leaderboard for your server.

### Features

- Auto-detects official Wordle share messages (text or screenshots) that are posted in the configured channel.
- Records wins, losses, total attempts, and per-guess distribution for each player.
- `!wordle_stats [@member]` shows a personal stat card with win rate and guess distribution.
- `!wordle_leaderboard` displays the top performers ordered by win rate and average attempts.
- Optional daily leaderboard post that fires automatically after the puzzle resets.
- `!wordle_backfill [limit]` (requires Manage Server) scrapes historical Wordle posts to catch up stats.

### Requirements

- Python 3.10+
- Tesseract OCR installed and accessible on `PATH` (already included in the Docker image).
- A Discord bot token with the `MESSAGE CONTENT INTENT` enabled.
- The numeric ID of the Wordle channel in your server.
- Bot role permissions: Read Messages, Send Messages, Read Message History (for backfill).

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` into a `.env` file and fill in the values:

```
DISCORD_TOKEN=bot-token
WORDLE_CHANNEL_ID=123456789012345678
DATA_PATH=./data/wordle_stats.json  # optional
COMMAND_PREFIX=!
LEADERBOARD_SIZE=10
LEADERBOARD_POST_TIME=00:05        # optional, HH:MM UTC to auto-post the leaderboard
LEADERBOARD_POST_CHANNEL_ID=123... # optional, defaults to WORDLE_CHANNEL_ID
```

The bot uses the channel ID to decide which messages count toward the stats. The `DATA_PATH` can be changed if you want to store the JSON file elsewhere.
If `LEADERBOARD_POST_TIME` is set (HH:MM in 24-hour UTC), the bot will send the leaderboard embed every day at that time to `LEADERBOARD_POST_CHANNEL_ID` (or the Wordle channel if unspecified).

### Running the bot

```bash
python -m wordler_bot.bot
```

The bot logs to stdout. Stop it with `Ctrl+C`.

### Running with Docker

Build the image:

```bash
docker build -t wordler-bot .
```

Create a `.env` file (see `.env.example`) and run the container, mounting a host directory for persistent stats:

```bash
mkdir -p data
docker run --rm \\
  --env-file .env \\
  -v $(pwd)/data:/app/data \\
  wordler-bot
```

The `DATA_PATH` inside the container should point to `/app/data/wordle_stats.json` (default) so the volume stores your stats outside the container. Attach the container to a process manager or orchestration platform for continuous hosting.

### Notes

- Only messages in the configured channel are parsed.
- Duplicate posts for the same puzzle are counted separately; delete the original message if you need to remove a result.
- The JSON store (`DATA_PATH`) can be backed up or edited manually if needed.
- Use `!wordle_backfill 500` (or another limit) in the Wordle channel to import historical results after first installing the bot.
- Screenshot parsing relies on Tesseract OCR; install it locally if you are not using the provided Docker image.

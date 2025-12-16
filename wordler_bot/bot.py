from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from .config import BotSettings, SettingsError
from .parser import DailySummaryEntry, WordleResult, parse_daily_summary, parse_wordle_image, parse_wordle_message
from .stats import StatsManager, UserSummary

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def format_distribution(summary: UserSummary) -> str:
    parts = []
    for i in range(1, 7):
        count = summary.guess_distribution.get(str(i), 0)
        parts.append(f"{i}:{count}")
    return " | ".join(parts)


def build_leaderboard_embed(entries: list[UserSummary]) -> discord.Embed:
    def shorten(name: str, limit: int = 18) -> str:
        if len(name) <= limit:
            return name
        return name[: limit - 3] + "..."

    header = f"{'#':>2} {'Player':<18} {'Avg':>6} {'Wins':>6} {'Games':>7} {'Win%':>7}"
    divider = "-" * len(header)
    lines = [header, divider]
    for index, entry in enumerate(entries, start=1):
        avg = f"{entry.average_attempts:.2f}" if entry.average_attempts is not None else "n/a"
        win_pct = f"{entry.win_rate * 100:.1f}"
        lines.append(
            f"{index:>2} {shorten(entry.display_name):<18} {avg:>6} {entry.wins:>6} {entry.games_played:>7} {win_pct:>7}"
        )
    table = "\n".join(lines)
    embed = discord.Embed(
        title="Wordle Leaderboard",
        description=f"```\n{table}\n```",
        color=discord.Color.gold(),
    )
    return embed


def create_bot(settings: BotSettings, stats_manager: StatsManager) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    bot = commands.Bot(command_prefix=settings.command_prefix, intents=intents)

    @bot.event
    async def on_ready():
        logger.info("Logged in as %s (id=%s)", bot.user, getattr(bot.user, "id", "n/a"))

    async def process_daily_summary(message: discord.Message) -> tuple[bool, int, int]:
        entries: list[DailySummaryEntry] = parse_daily_summary(message.content)
        if not entries:
            return False, 0, 0

        mention_map = {member.id: member for member in message.mentions}

        async def resolve_member(entry: DailySummaryEntry) -> discord.Member | discord.User | None:
            member = None
            if entry.user_id is not None:
                member = mention_map.get(entry.user_id)
                if member is None and message.guild is not None:
                    member = message.guild.get_member(entry.user_id)
                if member is None and message.guild is not None:
                    try:
                        member = await message.guild.fetch_member(entry.user_id)
                    except discord.DiscordException as exc:
                        logger.debug("Failed to fetch member %s from summary %s: %s", entry.user_id, message.id, exc)
                if member is not None:
                    return member

            handle = (entry.handle or "").lstrip("@").strip()
            if not handle or message.guild is None:
                return None

            member = message.guild.get_member_named(handle)
            if member:
                return member

            lower_handle = handle.lower()

            def _matches(candidate: discord.Member) -> bool:
                names = [candidate.display_name, candidate.name]
                if candidate.global_name:
                    names.append(candidate.global_name)
                for name in names:
                    if name and name.lower() == lower_handle:
                        return True
                return False

            if getattr(message.guild, "chunked", False):
                member = discord.utils.find(_matches, message.guild.members)
                if member:
                    return member

            if hasattr(message.guild, "query_members"):
                try:
                    results = await message.guild.query_members(query=handle, limit=5)
                except discord.DiscordException as exc:
                    logger.debug("Failed to query members for handle %s: %s", handle, exc)
                    return None

                for candidate in results:
                    if _matches(candidate):
                        return candidate

                return results[0] if results else None

            return None

        recorded = 0
        skipped = 0
        for entry in entries:
            member = await resolve_member(entry)
            if member is None:
                identifier = entry.user_id if entry.user_id is not None else entry.handle or "unknown"
                logger.debug("Skipping summary entry for unknown member %s in message %s", identifier, message.id)
                skipped += 1
                continue

            result = WordleResult(
                puzzle_number=None,
                success=entry.success,
                attempts=entry.attempts,
                hard_mode=False,
                board=[],
            )
            dedupe_key = f"{message.id}:{member.id}"
            success = await stats_manager.record_result(member, result, message_key=dedupe_key)
            if success:
                recorded += 1
            else:
                skipped += 1

        return True, recorded, skipped

    @bot.event
    async def on_message(message: discord.Message):
        if bot.user and message.author.id == bot.user.id:
            return

        await bot.process_commands(message)

        if message.channel.id != settings.wordle_channel_id:
            return

        handled_summary, _, _ = await process_daily_summary(message)
        if handled_summary:
            return

        result = parse_wordle_message(message.content)
        if not result:
            for attachment in message.attachments:
                if attachment.size > 6 * 1024 * 1024:
                    continue
                content_type = attachment.content_type or ""
                if attachment.filename and not content_type and attachment.filename.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp")
                ):
                    content_type = "image/unknown"
                if not content_type.startswith("image/"):
                    continue
                try:
                    payload = await attachment.read()
                except discord.DiscordException as exc:
                    logger.warning("Failed to read attachment %s: %s", attachment.id, exc)
                    continue
                result = parse_wordle_image(payload)
                if result:
                    break
            if not result:
                return

        await stats_manager.record_result(message.author, result, message_id=message.id)

    def is_wordle_channel(ctx: commands.Context) -> bool:
        return ctx.channel.id == settings.wordle_channel_id

    @bot.command(name="wordle_stats")
    @commands.check(is_wordle_channel)
    async def wordle_stats(ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        summary = stats_manager.get_user_summary(target.id)
        if not summary:
            await ctx.send(f"No Wordle results found for {target.display_name} yet.")
            return

        embed = discord.Embed(
            title=f"Wordle stats for {summary.display_name}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Games played", value=str(summary.games_played))
        embed.add_field(name="Wins", value=str(summary.wins))
        embed.add_field(name="Win rate", value=f"{summary.win_rate * 100:.1f}%")
        if summary.average_attempts is not None:
            embed.add_field(name="Avg attempts", value=f"{summary.average_attempts:.2f}")
        embed.add_field(name="Distribution", value=format_distribution(summary), inline=False)
        if summary.last_puzzle is not None:
            embed.set_footer(text=f"Latest puzzle #{summary.last_puzzle}")

        await ctx.send(embed=embed)

    @bot.command(name="wordle_leaderboard")
    @commands.check(is_wordle_channel)
    async def wordle_leaderboard(ctx: commands.Context):
        await send_leaderboard_embed(ctx.channel)

    async def send_leaderboard_embed(channel: discord.abc.Messageable):
        entries = stats_manager.leaderboard(limit=settings.leaderboard_size)
        if not entries:
            await channel.send("No Wordle games recorded yet.")
            return
        embed = build_leaderboard_embed(entries)
        await channel.send(embed=embed)

    @bot.command(name="wordle_backfill")
    @commands.check(is_wordle_channel)
    @commands.has_permissions(manage_guild=True)
    async def wordle_backfill(ctx: commands.Context, limit: int | None = None):
        max_messages = limit or 1000
        await ctx.send(f"Backfilling Wordle results from the last {max_messages} messages...")
        recorded = 0
        skipped = 0
        async for message in ctx.channel.history(limit=max_messages):
            if bot.user and message.author.id == bot.user.id:
                continue

            handled_summary, rec_delta, skip_delta = await process_daily_summary(message)
            if handled_summary:
                recorded += rec_delta
                skipped += skip_delta
                continue

            result = parse_wordle_message(message.content)
            if not result:
                continue
            success = await stats_manager.record_result(message.author, result, message_id=message.id)
            if success:
                recorded += 1
            else:
                skipped += 1
        await ctx.send(f"Backfill complete: {recorded} new results recorded, {skipped} duplicates skipped.")

    leaderboard_channel_id = settings.leaderboard_post_channel_id or settings.wordle_channel_id

    if settings.leaderboard_post_time:

        @tasks.loop(time=settings.leaderboard_post_time)
        async def daily_leaderboard():
            channel = bot.get_channel(leaderboard_channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(leaderboard_channel_id)
                except discord.DiscordException as exc:
                    logger.warning("Could not fetch leaderboard channel %s: %s", leaderboard_channel_id, exc)
                    return
            await send_leaderboard_embed(channel)

        @daily_leaderboard.before_loop
        async def before_daily_leaderboard():
            await bot.wait_until_ready()

        daily_leaderboard.start()

    return bot


def main():
    try:
        settings = BotSettings.from_env()
    except SettingsError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    stats_manager = StatsManager(settings.data_path)
    stats_manager.load()

    bot = create_bot(settings, stats_manager)
    bot.run(settings.token)


if __name__ == "__main__":
    main()

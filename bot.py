"""
Main entrypoint. Connects to Discord, watches the channels listed in
config.json, and sends a daily digest DM (with PDF attachment) to your
configured recipients.
"""

import os
import json
import asyncio
import datetime

import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv

from storage import init_db, add_item
from digest import send_daily_report

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

with open("config.json") as f:
    CONFIG = json.load(f)

# Build a lookup: channel_id (int) -> {guild_name, channel_name, category}
WATCHED_CHANNELS = {}
for guild_cfg in CONFIG["guilds"]:
    for ch in guild_cfg["channels"]:
        WATCHED_CHANNELS[int(ch["id"])] = {
            "guild_name": guild_cfg["name"],
            "channel_name": ch["name"],
            "category": ch["category"],
        }

RECIPIENTS = CONFIG["recipients"]
REPORT_HOUR = CONFIG.get("report_hour_utc", 13)
REPORT_MINUTE = CONFIG.get("report_minute_utc", 0)

# Domains that count as an "external livestream" if linked in a watched channel
LIVESTREAM_DOMAINS = ("twitch.tv", "youtube.com/live", "youtu.be", "kick.com")

intents = discord.Intents.default()
intents.message_content = True   # privileged - must be enabled in the Dev Portal too
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not daily_report_task.is_running():
        daily_report_task.start()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    watch = WATCHED_CHANNELS.get(message.channel.id)
    if not watch:
        return

    if not message.content and not message.embeds:
        return

    category = watch["category"]
    content_lower = message.content.lower()

    # Auto-promote to "livestreams" if a stream link shows up in any watched channel
    if any(domain in content_lower for domain in LIVESTREAM_DOMAINS):
        category = "livestreams"

    add_item(
        guild_name=watch["guild_name"],
        channel_name=watch["channel_name"],
        category=category,
        author=str(message.author),
        content=message.content or "[embed/attachment]",
        url=message.jump_url,
    )


@bot.event
async def on_voice_state_update(member: discord.Member, before, after):
    """Detects Discord's native 'Go Live' screen-share streams."""
    guild_cfg = next((g for g in CONFIG["guilds"] if g["id"] == str(member.guild.id)), None)
    if not guild_cfg or not guild_cfg.get("track_native_streams", False):
        return

    if not before.self_stream and after.self_stream:
        add_item(
            guild_name=member.guild.name,
            channel_name=after.channel.name if after.channel else "unknown",
            category="livestreams",
            author=str(member),
            content=f"{member} started streaming live on Discord.",
            url="",
        )


@tasks.loop(hours=24)
async def daily_report_task():
    # Pull each watched guild's upcoming scheduled events before building the report
    for guild_cfg in CONFIG["guilds"]:
        guild = bot.get_guild(int(guild_cfg["id"]))
        if not guild:
            continue
        try:
            events = await guild.fetch_scheduled_events()
        except discord.HTTPException:
            events = []
        for event in events:
            add_item(
                guild_name=guild.name,
                channel_name="Scheduled Events",
                category="events",
                author=event.creator.name if event.creator else "unknown",
                content=f"{event.name} — starts {event.start_time.strftime('%b %d, %I:%M %p UTC')}",
                url=event.url,
            )

    await send_daily_report(bot, RECIPIENTS)


@daily_report_task.before_loop
async def before_daily_report():
    await bot.wait_until_ready()
    now = datetime.datetime.now(datetime.timezone.utc)
    target = now.replace(hour=REPORT_HOUR, minute=REPORT_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    await asyncio.sleep((target - now).total_seconds())


if __name__ == "__main__":
    init_db()
    bot.run(TOKEN)

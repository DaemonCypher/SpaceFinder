import discord
import asyncio
import os
from discord.ext import tasks, commands

# Read the token and channel ID from environment variables
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# Intents are required in discord.py v2. Make sure to enable the intents you need in the Discord Developer Portal.
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Send a notification every hour as an example
@tasks.loop(hours=1)
async def send_notification():
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("You got this! Keep going!👊")

# Start the notification loop once the bot is ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    send_notification.start()

# You can also add a command to trigger a notification manually
@bot.command(name='notify')
async def notify(ctx):
    await ctx.send("This is a manual notification!")

# Run the bot
bot.run(TOKEN)

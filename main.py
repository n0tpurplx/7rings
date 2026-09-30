import os
import discord
from discord.ext import commands
intents = discord.Intents.default()
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! `{latency}ms`")
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
bot.run(token)

Install the dependency:

pip install discord.py

Then run:

python bot.py

Make sure your environment contains:

DISCORD_TOKEN=your_bot_token_here

The /ping command will be registered globally through Discord’s application command system.import os
import discord
from discord.ext import commands
intents = discord.Intents.default()
bot = commands.Bot(
    command_prefix="!",
    intents=intents
)
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! `{latency}ms`")
token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN environment variable is not set.")
bot.run(token)

Install the dependency:

pip install discord.py

Then run:

python bot.py

Make sure your environment contains:

DISCORD_TOKEN=your_bot_token_here

The /ping command will be registered globally through Discord’s application command system.

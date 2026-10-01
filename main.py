
import os
import json
import logging
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ---------------- CONFIGURATION ----------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ERLC_KEY = os.getenv("ERLC_KEY")

API_URL = "https://api.erlc.gg/v2/server"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erlc-bot")


# ---------------- ER:LC API CLIENT ----------------

class ERLCAPI:
    def __init__(self):
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers={
                "server-key": ERLC_KEY,
                "Accept": "application/json",
                "User-Agent": "ERLC-Discord-Bot/1.0",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_server(
        self,
        players=False,
        staff=False,
        vehicles=False,
    ):
        if not self.session:
            raise RuntimeError("API session is not initialized.")

        params = {}

        if players:
            params["Players"] = "true"

        if staff:
            params["Staff"] = "true"

        if vehicles:
            params["Vehicles"] = "true"

        async with self.session.get(
            API_URL,
            params=params,
        ) as response:

            body = await response.text()

            if response.status != 200:
                raise RuntimeError(
                    f"ER:LC API returned HTTP {response.status}: "
                    f"{body[:400]}"
                )

            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError("ER:LC returned invalid JSON.")


api = ERLCAPI()


# ---------------- DATA HELPERS ----------------

def get_value(data: Any, *keys, default=None):
    """Find a field without depending on capitalization."""

    if not isinstance(data, dict):
        return default

    normalized = {
        str(key).lower(): value
        for key, value in data.items()
    }

    for key in keys:
        if key.lower() in normalized:
            return normalized[key.lower()]

    return default


def get_collection(data: Any, *names):
    """
    Extract a collection from a response.
    Supports arrays, nested objects, and capitalization differences.
    """

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    value = get_value(data, *names)

    if isinstance(value, list):
        return value

    if isinstance(value, dict):
        return list(value.values())

    return []


def display(value):
    if value is None:
        return "Unknown"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def add_field(embed, name, value, inline=False):
    value = display(value)

    if len(value) > 1024:
        value = value[:1021] + "..."

    embed.add_field(
        name=name,
        value=value,
        inline=inline,
    )


def make_embed(title, description=None):
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_rgb(130, 75, 220),
    )


def find_player(players, username):
    username = username.casefold()

    for player in players:
        name = get_value(player, "Player", "Username", "Name")

        if name and str(name).casefold() == username:
            return player

    return None


# ---------------- BOT ----------------

class ERLCBot(commands.Bot):

    def __init__(self):
        intents = discord.Intents.default()

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self):
        await api.start()

        synced = await self.tree.sync()

        logger.info(
            "Synced %s application commands.",
            len(synced),
        )

    async def close(self):
        await api.close()
        await super().close()


bot = ERLCBot()


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)


# ---------------- COMMANDS ----------------

@bot.tree.command(
    name="server",
    description="View ER:LC server information.",
)
async def server(interaction: discord.Interaction):

    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server()

        embed = make_embed("ER:LC Server Information")

        if isinstance(data, dict):
            # Display scalar fields returned by the API.
            for key, value in data.items():

                if isinstance(value, (dict, list)):
                    continue

                add_field(
                    embed,
                    str(key),
                    value,
                    inline=True,
                )

        if not embed.fields:
            embed.description = "The API returned no displayable server fields."

        await interaction.followup.send(embed=embed)

    except Exception as error:
        logger.exception("Server command failed")
        await interaction.followup.send(
            f"Could not retrieve server information:\n`{str(error)[:1500]}`",
            ephemeral=True,
        )


@bot.tree.command(
    name="players",
    description="View players currently in the server.",
)
async def players_command(interaction: discord.Interaction):

    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(players=True)

        players = get_collection(data, "Players")

        embed = make_embed(
            "Players Online",
            f"Currently returned by the API: **{len(players)}**",
        )

        if not players:
            embed.description = "No players were returned."

        for player in players[:25]:

            name = get_value(player, "Player", "Username", "Name", default="Unknown")
            team = get_value(player, "Team", default="Unknown")
            callsign = get_value(player, "Callsign", default="None")

            embed.add_field(
                name=str(name)[:256],
                value=(
                    f"**Team:** {display(team)}\n"
                    f"**Callsign:** {display(callsign)}"
                ),
                inline=True,
            )

        if len(players) > 25:
            embed.set_footer(
                text=f"Showing 25 of {len(players)} players."
            )

        await interaction.followup.send(embed=embed)

    except Exception as error:
        logger.exception("Players command failed")
        await interaction.followup.send(
            f"Could not retrieve players:\n`{str(error)[:1500]}`",
            ephemeral=True,
        )


@bot.tree.command(
    name="playerinfo",
    description="View information about a player.",
)
@app_commands.describe(username="The exact in-game username")
async def playerinfo(
    interaction: discord.Interaction,
    username: str,
):

    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(
            players=True,
            vehicles=True,
        )

        player_list = get_collection(data, "Players")
        vehicle_list = get_collection(data, "Vehicles")

        player = find_player(player_list, username)

        if not player:
            await interaction.followup.send(
                f"Player `{username}` was not found in the server.",
                ephemeral=True,
            )
            return

        name = get_value(player, "Player", "Username", "Name", default=username)

        embed = make_embed(
            f"Player Information: {name}"
        )

        add_field(embed, "Team", get_value(player, "Team"))
        add_field(embed, "Callsign", get_value(player, "Callsign"))
        add_field(embed, "Permission", get_value(player, "Permission"))

        wanted = get_value(player, "WantedStars")

        if wanted is not None:
            add_field(embed, "Wanted Stars", wanted)

        location = get_value(player, "Location")

        if location is not None:
            if isinstance(location, dict):
                postal = get_value(location, "Postal", "PostalCode")
                street = get_value(location, "Street", "StreetName")
                building = get_value(location, "Building", "BuildingNumber")
                x = get_value(location, "X")
                y = get_value(location, "Y")

                location_parts = []

                if postal is not None:
                    location_parts.append(f"Postal: {postal}")

                if street is not None:
                    location_parts.append(f"Street: {street}")

                if building is not None:
                    location_parts.append(f"Building: {building}")

                if x is not None or y is not None:
                    location_parts.append(f"Coordinates: {x}, {y}")

                add_field(
                    embed,
                    "Location",
                    "\n".join(location_parts) or display(location),
                )
            else:
                add_field(embed, "Location", location)

        owned_vehicles = []

        for vehicle in vehicle_list:
            owner = get_value(vehicle, "Owner")

            if owner and str(owner).casefold() == str(name).casefold():
                owned_vehicles.append(vehicle)

        if owned_vehicles:
            vehicle_text = []

            for vehicle in owned_vehicles[:10]:
                vehicle_name = get_value(vehicle, "Name", default="Unknown")
                plate = get_value(vehicle, "Plate", default="Unknown")

                vehicle_text.append(
                    f"**{vehicle_name}**\nPlate: `{plate}`"
                )

            add_field(
                embed,
                "Spawned Vehicle(s)",
                "\n\n".join(vehicle_text),
            )
        else:
            add_field(
                embed,
                "Spawned Vehicle(s)",
                "No matching spawned vehicle was returned.",
            )

        await interaction.followup.send(embed=embed)

    except Exception as error:
        logger.exception("Player info command failed")
        await interaction.followup.send(
            f"Could not retrieve player information:\n`{str(error)[:1500]}`",
            ephemeral=True,
        )


@bot.tree.command(
    name="vehicles",
    description="View currently spawned vehicles.",
)
async def vehicles_command(interaction: discord.Interaction):

    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(vehicles=True)

        vehicles = get_collection(data, "Vehicles")

        embed = make_embed(
            "Spawned Vehicles",
            f"Vehicles returned by the API: **{len(vehicles)}**",
        )

        if not vehicles:
            embed.description = "No vehicles were returned."

        for vehicle in vehicles[:25]:

            name = get_value(vehicle, "Name", default="Unknown")
            owner = get_value(vehicle, "Owner", default="Unknown")
            plate = get_value(vehicle, "Plate", default="Unknown")
            color = get_value(vehicle, "ColorName", default="Unknown")

            embed.add_field(
                name=str(name)[:256],
                value=(
                    f"**Owner:** {display(owner)}\n"
                    f"**Plate:** {display(plate)}\n"
                    f"**Color:** {display(color)}"
                ),
                inline=True,
            )

        await interaction.followup.send(embed=embed)

    except Exception as error:
        logger.exception("Vehicles command failed")
        await interaction.followup.send(
            f"Could not retrieve vehicles:\n`{str(error)[:1500]}`",
            ephemeral=True,
        )


@bot.tree.command(
    name="staff",
    description="View server staff.",
)
async def staff_command(interaction: discord.Interaction):

    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(staff=True)

        staff_members = get_collection(data, "Staff")

        embed = make_embed(
            "Server Staff",
            f"Staff entries returned: **{len(staff_members)}**",
        )

        if not staff_members:
            embed.description = "No staff entries were returned."

        for member in staff_members[:25]:

            name = get_value(
                member,
                "Player",
                "Username",
                "Name",
                default="Unknown",
            )

            permission = get_value(
                member,
                "Permission",
                "Rank",
                default="Unknown",
            )

            embed.add_field(
                name=str(name)[:256],
                value=f"**Permission:** {display(permission)}",
                inline=True,
            )

        await interaction.followup.send(embed=embed)

    except Exception as error:
        logger.exception("Staff command failed")
        await interaction.followup.send(
            f"Could not retrieve staff:\n`{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- START ----------------

if not DISCORD_TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable.")

if not ERLC_KEY:
    raise RuntimeError("Missing ERLC_KEY environment variable.")

bot.run(DISCORD_TOKEN)

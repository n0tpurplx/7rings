import os
import json
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ERLC_KEY = os.getenv("ERLC_KEY")

API_URL = "https://api.erlc.gg/v2/server"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erlc-bot")


class ERLCAPI:
    def __init__(self):
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers={
                "server-key": ERLC_KEY,
                "Accept": "application/json",
            },
            timeout=aiohttp.ClientTimeout(total=20),
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def get_server(self, **options):
        params = {
            key: "true"
            for key, enabled in options.items()
            if enabled
        }

        async with self.session.get(
            API_URL,
            params=params,
        ) as response:

            body = await response.text()

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"raw": body}

            if response.status != 200:
                raise RuntimeError(
                    f"HTTP {response.status}: "
                    f"{json.dumps(data, ensure_ascii=False)[:1200]}"
                )

            return data


api = ERLCAPI()


class ERLCBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=discord.Intents.default(),
        )

    async def setup_hook(self):
        await api.start()

        synced = await self.tree.sync()
        logger.info("Synced %s slash commands", len(synced))

    async def close(self):
        await api.close()
        await super().close()


bot = ERLCBot()


@bot.event
async def on_ready():
    logger.info("Logged in as %s", bot.user)


def embed(title, description=None):
    return discord.Embed(
        title=title,
        description=description,
        color=discord.Color.from_rgb(130, 75, 220),
    )


def field(e, name, value, inline=False):
    if value is None:
        value = "Unknown"

    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)

    value = str(value)

    if len(value) > 1024:
        value = value[:1021] + "..."

    e.add_field(
        name=name,
        value=value,
        inline=inline,
    )


def player_name(player):
    return str(player.get("Player", "Unknown")).split(":")[0]


def find_player(players, username):
    return next(
        (
            p for p in players
            if player_name(p).casefold() == username.casefold()
            or str(p.get("Player", "")).casefold() == username.casefold()
        ),
        None,
    )


# ---------------- SERVER ----------------

@bot.tree.command(
    name="server",
    description="View ER:LC server information.",
)
async def server(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server()

        e = embed("ER:LC Server")

        fields = [
            ("Name", data.get("Name")),
            ("Owner ID", data.get("OwnerId")),
            ("Current Players", data.get("CurrentPlayers")),
            ("Maximum Players", data.get("MaxPlayers")),
            ("Join Key", data.get("JoinKey")),
            ("Account Verification", data.get("AccVerifiedReq")),
            ("Team Balance", data.get("TeamBalance")),
        ]

        for name, value in fields:
            field(e, name, value, inline=True)

        await interaction.followup.send(embed=e)

    except Exception as error:
        logger.exception("Server command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- PLAYERS ----------------

@bot.tree.command(
    name="players",
    description="List players currently in the server.",
)
async def players(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(Players=True)
        player_list = data.get("Players", [])

        e = embed(
            "Players Online",
            f"**{len(player_list)}** player(s) returned by the API.",
        )

        if not player_list:
            e.description = "No players are currently online."

        for p in player_list[:25]:
            name = player_name(p)

            e.add_field(
                name=name[:256],
                value=(
                    f"**Team:** {p.get('Team', 'Unknown')}\n"
                    f"**Callsign:** {p.get('Callsign', 'None')}\n"
                    f"**Permission:** {p.get('Permission', 'Normal')}"
                ),
                inline=True,
            )

        await interaction.followup.send(embed=e)

    except Exception as error:
        logger.exception("Players command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- PLAYER INFO ----------------

@bot.tree.command(
    name="playerinfo",
    description="View detailed information about a player.",
)
@app_commands.describe(username="The player's Roblox username")
async def playerinfo(
    interaction: discord.Interaction,
    username: str,
):
    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(
            Players=True,
            Vehicles=True,
        )

        player_list = data.get("Players", [])
        vehicle_list = data.get("Vehicles", [])

        p = find_player(player_list, username)

        if not p:
            await interaction.followup.send(
                f"`{username}` is not currently in the server.",
                ephemeral=True,
            )
            return

        e = embed(f"Player Information: {player_name(p)}")

        field(e, "Team", p.get("Team"))
        field(e, "Callsign", p.get("Callsign"))
        field(e, "Permission", p.get("Permission"))
        field(e, "Wanted Stars", p.get("WantedStars", 0))

        location = p.get("Location", {})

        if location:
            field(
                e,
                "Location",
                (
                    f"**Street:** {location.get('StreetName', 'Unknown')}\n"
                    f"**Building:** {location.get('BuildingNumber', 'Unknown')}\n"
                    f"**Postal Code:** {location.get('PostalCode', 'Unknown')}\n"
                    f"**X:** {location.get('LocationX', 'Unknown')}\n"
                    f"**Z:** {location.get('LocationZ', 'Unknown')}"
                ),
            )

        matching = [
            v for v in vehicle_list
            if str(v.get("Owner", "")).casefold()
            == player_name(p).casefold()
        ]

        if matching:
            for v in matching[:5]:
                field(
                    e,
                    f"Vehicle: {v.get('Name', 'Unknown')}",
                    (
                        f"**Plate:** {v.get('Plate', 'Unknown')}\n"
                        f"**Texture:** {v.get('Texture', 'None')}\n"
                        f"**Color:** {v.get('ColorName', 'Unknown')}"
                    ),
                )
        else:
            field(e, "Spawned Vehicle", "No matching vehicle found.")

        await interaction.followup.send(embed=e)

    except Exception as error:
        logger.exception("Player info command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- VEHICLES ----------------

@bot.tree.command(
    name="vehicles",
    description="List currently spawned vehicles.",
)
async def vehicles(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(Vehicles=True)
        vehicle_list = data.get("Vehicles", [])

        e = embed(
            "Spawned Vehicles",
            f"**{len(vehicle_list)}** vehicle(s) returned.",
        )

        for v in vehicle_list[:25]:
            e.add_field(
                name=str(v.get("Name", "Unknown"))[:256],
                value=(
                    f"**Owner:** {v.get('Owner', 'Unknown')}\n"
                    f"**Plate:** {v.get('Plate', 'Unknown')}\n"
                    f"**Color:** {v.get('ColorName', 'Unknown')}\n"
                    f"**Texture:** {v.get('Texture', 'None')}"
                ),
                inline=True,
            )

        await interaction.followup.send(embed=e)

    except Exception as error:
        logger.exception("Vehicles command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- STAFF ----------------

@bot.tree.command(
    name="staff",
    description="List server administrators, moderators, and helpers.",
)
async def staff(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    try:
        data = await api.get_server(Staff=True)
        staff_data = data.get("Staff", {})

        e = embed("Server Staff")

        for role in ("Admins", "Mods", "Helpers"):
            members = staff_data.get(role, {})

            if isinstance(members, dict):
                lines = [
                    f"`{user_id}` - {username}"
                    for user_id, username in members.items()
                ]
            else:
                lines = []

            field(
                e,
                role,
                "\n".join(lines) if lines else "None listed.",
            )

        await interaction.followup.send(embed=e)

    except Exception as error:
        logger.exception("Staff command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


# ---------------- DEBUG ----------------

@bot.tree.command(
    name="debug",
    description="Inspect the raw ER:LC V2 server response.",
)
async def debug(interaction: discord.Interaction):
    await interaction.response.defer(
        thinking=True,
        ephemeral=True,
    )

    try:
        data = await api.get_server(
            Staff=True,
            Players=True,
            Vehicles=True,
            EmergencyCalls=True,
            ModCalls=True,
            CommandLogs=True,
            KillLogs=True,
            Queue=True,
            JoinLogs=True,
        )

        result = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )

        if len(result) > 1800:
            result = result[:1800] + "\n... response truncated"

        await interaction.followup.send(
            f"```json\n{result}\n```",
            ephemeral=True,
        )

    except Exception as error:
        logger.exception("Debug command failed")
        await interaction.followup.send(
            f"API error: `{str(error)[:1500]}`",
            ephemeral=True,
        )


if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

if not ERLC_KEY:
    raise RuntimeError("ERLC_KEY is missing.")

bot.run(DISCORD_TOKEN)


import os
import aiohttp
import discord

from discord.ext import commands

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ERLC_KEY = os.getenv("ERLC_KEY")

API_BASE = "https://api.erlc.gg/v2"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


class ERLC:
    def __init__(self):
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession(
            headers={
                "server-key": ERLC_KEY,
                "Accept": "application/json"
            },
            timeout=aiohttp.ClientTimeout(total=15)
        )

    async def close(self):
        if self.session:
            await self.session.close()

    async def get(self, endpoint):
        async with self.session.get(
            f"{API_BASE}/{endpoint}"
        ) as response:

            if response.status == 429:
                raise RuntimeError("ER:LC API rate limit reached.")

            if response.status == 401:
                raise RuntimeError("Invalid ERLC_KEY.")

            if response.status == 403:
                raise RuntimeError("API access forbidden.")

            if response.status != 200:
                raise RuntimeError(
                    f"ER:LC API returned HTTP {response.status}."
                )

            return await response.json()


erlc = ERLC()


def get_value(data, *keys, default="Unknown"):
    for key in keys:
        if isinstance(data, dict) and data.get(key) is not None:
            return data[key]

    return default


def format_value(value):
    if value is None:
        return "Unknown"

    if isinstance(value, (dict, list)):
        return str(value)

    return str(value)


def make_embed(title, description=None):
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blurple()
    )

    embed.set_footer(text="EasyERLC | Read-only API")
    return embed


async def send_error(interaction, error):
    message = f"**ER:LC API error:** {error}"

    if interaction.response.is_done():
        await interaction.followup.send(
            message,
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            message,
            ephemeral=True
        )


@bot.event
async def setup_hook():
    await erlc.start()

    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} slash commands")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.tree.command(
    name="server",
    description="View ER:LC server information"
)
async def server(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await erlc.get("server")

        embed = make_embed("ER:LC Server Status")

        embed.add_field(
            name="Server Name",
            value=format_value(
                get_value(data, "Name", "ServerName")
            ),
            inline=False
        )

        embed.add_field(
            name="Players",
            value=format_value(
                get_value(data, "CurrentPlayers", "Players")
            ),
            inline=True
        )

        embed.add_field(
            name="Join Key",
            value=format_value(
                get_value(data, "JoinKey")
            ),
            inline=True
        )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await send_error(interaction, e)


@bot.tree.command(
    name="players",
    description="List players currently in the ER:LC server"
)
async def players(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await erlc.get("server/players")

        if not isinstance(data, list):
            raise RuntimeError("Unexpected players response format.")

        embed = make_embed(
            f"Players Online ({len(data)})"
        )

        if not data:
            embed.description = "No players are currently online."

        for player in data[:25]:
            username = get_value(player, "Player")
            team = get_value(player, "Team")
            permission = get_value(player, "Permission")
            callsign = get_value(player, "Callsign", default="None")

            embed.add_field(
                name=str(username),
                value=(
                    f"**Team:** {team}\n"
                    f"**Permission:** {permission}\n"
                    f"**Callsign:** {callsign}"
                ),
                inline=True
            )

        if len(data) > 25:
            embed.set_footer(
                text=f"Showing 25 of {len(data)} players"
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await send_error(interaction, e)


@bot.tree.command(
    name="playerinfo",
    description="View detailed information about an ER:LC player"
)
async def playerinfo(
    interaction: discord.Interaction,
    username: str
):
    await interaction.response.defer()

    try:
        players_data = await erlc.get("server/players")
        vehicles_data = await erlc.get("server/vehicles")

        if not isinstance(players_data, list):
            raise RuntimeError("Unexpected players response format.")

        if not isinstance(vehicles_data, list):
            vehicles_data = []

        matches = [
            player for player in players_data
            if username.lower() in str(
                get_value(player, "Player", default="")
            ).lower()
        ]

        if not matches:
            await interaction.followup.send(
                f"No online player matching `{username}` was found.",
                ephemeral=True
            )
            return

        player = matches[0]

        player_name = get_value(player, "Player")

        owned_vehicles = [
            vehicle for vehicle in vehicles_data
            if str(get_value(
                vehicle, "Owner", "Player", default=""
            )).lower() == str(player_name).lower()
        ]

        embed = make_embed(
            f"Player Information: {player_name}"
        )

        embed.add_field(
            name="Player",
            value=str(player_name),
            inline=False
        )

        embed.add_field(
            name="Team",
            value=format_value(get_value(player, "Team")),
            inline=True
        )

        embed.add_field(
            name="Permission",
            value=format_value(get_value(player, "Permission")),
            inline=True
        )

        embed.add_field(
            name="Callsign",
            value=format_value(
                get_value(player, "Callsign", default="None")
            ),
            inline=True
        )

        embed.add_field(
            name="Wanted Status",
            value=format_value(
                get_value(player, "Wanted", "IsWanted")
            ),
            inline=True
        )

        embed.add_field(
            name="In-game Location",
            value=format_value(
                get_value(player, "Location", "Position")
            ),
            inline=True
        )

        if owned_vehicles:
            vehicle_lines = []

            for vehicle in owned_vehicles[:10]:
                vehicle_name = get_value(
                    vehicle, "Name", "Vehicle"
                )

                texture = get_value(
                    vehicle, "Texture", default="Default"
                )

                vehicle_lines.append(
                    f"**{vehicle_name}**\nTexture: {texture}"
                )

            vehicle_text = "\n\n".join(vehicle_lines)
        else:
            vehicle_text = "No matching vehicle information available."

        embed.add_field(
            name="Owned / Associated Vehicles",
            value=vehicle_text[:1024],
            inline=False
        )

        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await send_error(interaction, e)


@bot.tree.command(
    name="vehicles",
    description="View vehicle information from the ER:LC server"
)
async def vehicles(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await erlc.get("server/vehicles")

        if not isinstance(data, list):
            raise RuntimeError("Unexpected vehicles response format.")

        embed = make_embed(
            f"Server Vehicles ({len(data)})"
        )

        if not data:
            embed.description = "No vehicle records returned."

        for vehicle in data[:25]:
            embed.add_field(
                name=format_value(
                    get_value(vehicle, "Name", "Vehicle")
                ),
                value=(
                    f"**Owner:** {get_value(vehicle, 'Owner', 'Player')}\n"
                    f"**Texture:** {get_value(vehicle, 'Texture')}"
                ),
                inline=True
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await send_error(interaction, e)


@bot.tree.command(
    name="staff",
    description="View online ER:LC staff"
)
async def staff(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await erlc.get("server/players")

        staff_members = [
            player for player in data
            if str(get_value(
                player, "Permission", default=""
            )).lower() not in ("none", "normal", "unknown")
        ]

        embed = make_embed(
            f"Online Staff ({len(staff_members)})"
        )

        if not staff_members:
            embed.description = "No staff members identified."

        for member in staff_members[:25]:
            embed.add_field(
                name=str(get_value(member, "Player")),
                value=(
                    f"**Permission:** {get_value(member, 'Permission')}\n"
                    f"**Team:** {get_value(member, 'Team')}"
                ),
                inline=True
            )

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await send_error(interaction, e)


if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing.")

if not ERLC_KEY:
    raise RuntimeError("ERLC_KEY is missing.")

bot.run(DISCORD_TOKEN)

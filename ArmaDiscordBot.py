import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime, timezone

# ── CONFIG ─────────────────────────────────────────────────────────────────────
DISCORD_TOKEN       = "CHANGE ME" 		     			     # Put your Battlemetrics server ID
BATTLEMETRICS_TOKEN = "CHANGE ME"		  		    	     # Put your Battlemetrics server ID
SERVER_ID           = "CHANGE ME"    					     # Put your Battlemetrics server ID e.g. "12345678"
CHANNEL_ID          = CHANGE ME                          	  	     # Voice channel ID to rename (player count)
STATUS_CHANNEL_ID   = CHANGE ME                           		     # Text channel ID where embed auto-posts/deletes
UPDATE_INTERVAL     = CHANGE ME                          		     # Time when the status updates

# ── Roleplay server display name shown in embed title ─────────────────────────
RP_SERVER_NAME      = "CHANGE ME"        # e.g. "Arma RP | US-1"

BM_API  = f"https://api.battlemetrics.com/servers/CHANGE ME"  # Replace the CHANGE ME with the same SERVER_ID
HEADERS = {"Authorization": f"Bearer CHANGE ME"}	      # Replace the CHANGE ME with the same BATTLEMETRICS_TOKEN

# ── BOT SETUP ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# Stores the last posted status message so we can delete it
last_status_message: discord.Message | None = None

# ── API QUERY ─────────────────────────────────────────────────────────────────
async def get_server_info():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                BM_API,
                headers=HEADERS,
                params={"include": "player"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    print(f"[{ts()}] BattleMetrics returned {resp.status}")
                    return {"online": False}
                raw  = await resp.json()
                data = raw["data"]["attributes"]

        status      = data.get("status", "offline")
        players     = data.get("players", 0)
        max_players = data.get("maxPlayers", 0)
        server_name = data.get("name", RP_SERVER_NAME)
        ip          = data.get("ip", "?")
        port        = data.get("port", "?")
        details     = data.get("details", {})
        map_name    = details.get("map", "Glenwood Metro RP Map")
        rank        = data.get("rank", "N/A")
        queue       = details.get("queueSize", details.get("queue", 0))

        updated_raw = data.get("updatedAt")
        uptime_str  = "Unknown"
        if updated_raw:
            updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            now        = datetime.now(timezone.utc)
            diff       = now - updated_dt
            total_secs = int(diff.total_seconds())
            hours      = total_secs // 3600
            minutes    = (total_secs % 3600) // 60
            uptime_str = f"{hours}h {minutes}m"

        return {
            "online":      status == "online",
            "players":     players,
            "max_players": max_players,
            "server_name": server_name,
            "map":         map_name,
            "ip":          ip,
            "port":        port,
            "rank":        rank,
            "uptime":      uptime_str,
            "queue":       queue,
        }

    except asyncio.TimeoutError:
        print(f"[{ts()}] Request timed out.")
        return {"online": False}
    except Exception as e:
        print(f"[{ts()}] Error: {e}")
        return {"online": False}

def ts():
    return datetime.now().strftime("%H:%M:%S")

def player_bar(current, maximum, length=14):
    if maximum == 0:
        return "░" * length
    filled = int((current / maximum) * length)
    return "█" * filled + "░" * (length - filled)

# ── EMBED BUILDER ─────────────────────────────────────────────────────────────
def build_embed(info):
    now_str = datetime.now(timezone.utc).strftime("%m/%d/%Y %I:%M %p UTC")

    if not info["online"]:
        embed = discord.Embed(
            color=0xff4444,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_author(name=RP_SERVER_NAME, icon_url="https://i.imgur.com/wSTFkRM.png")
        embed.add_field(
            name="❌  Server Offline",
            value="The server is currently offline or restarting.\nCheck back shortly.",
            inline=False
        )
        embed.set_footer(text=f"Last checked: {now_str}")
        return embed

    bar         = player_bar(info["players"], info["max_players"])
    queue       = info["queue"]
    is_full     = info["players"] >= info["max_players"]
    color       = 0xff4444 if is_full else (0xffaa00 if info["players"] == 0 else 0x57f287)
    status_icon = "🔴" if is_full else "🟢"
    status_txt  = "**FULL**" if is_full else "**Online**"

    embed = discord.Embed(color=color, timestamp=datetime.now(timezone.utc))
    embed.set_author(name=RP_SERVER_NAME, icon_url="https://i.imgur.com/wSTFkRM.png")
    embed.title = f"{status_icon}  {info['server_name']}"

    embed.add_field(name="👥  Players",      value=f"**{info['players']}/{info['max_players']}**", inline=True)
    embed.add_field(name="🗺️  Map / Scenario", value=f"**{info['map'] or 'Unknown'}**",           inline=True)
    embed.add_field(name="\u200b",            value="\u200b",                                      inline=True)

    embed.add_field(name="📶  Server Status", value=status_txt,                  inline=True)
    embed.add_field(name="⏱️  Uptime",        value=f"**{info['uptime']}**",     inline=True)
    embed.add_field(name="\u200b",            value="\u200b",                    inline=True)

    embed.add_field(
        name=f"📊  Population  `[{bar}]`",
        value=f"{info['players']} players online out of {info['max_players']} slots",
        inline=False
    )

    queue_val = f"**{queue} players waiting**" if queue and queue > 0 else "**No queue**"
    embed.add_field(name="⏳  Queue",     value=queue_val,                         inline=True)
    embed.add_field(name="🔗  Direct Join", value=f"`{info['ip']}:{info['port']}`", inline=True)
    embed.add_field(name="\u200b",        value="\u200b",                           inline=True)

    if info["rank"] and info["rank"] != "N/A":
        embed.add_field(name="🏆  BattleMetrics Rank", value=f"**#{info['rank']}**", inline=True)

    embed.set_footer(text=f"Powered by BattleMetrics  •  Updates every {UPDATE_INTERVAL}s  •  {now_str}")
    return embed

# ── TASKS ──────────────────────────────────────────────────────────────────────
@tasks.loop(seconds=UPDATE_INTERVAL)
async def update_presence():
    info = await get_server_info()
    if info["online"]:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{info['players']}/{info['max_players']} players online"
        )
        await bot.change_presence(status=discord.Status.online, activity=activity)
    else:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="Server is offline ❌"
        )
        await bot.change_presence(status=discord.Status.idle, activity=activity)

@tasks.loop(seconds=UPDATE_INTERVAL)
async def update_channel_name():
    if CHANNEL_ID == 0:
        return
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
    info = await get_server_info()
    new_name = (
        f"🟢 ({info['players']}/{info['max_players']}) Players"
        if info["online"]
        else f"🔴 (0/{info.get('max_players', 128)}) Players"
    )
    try:
        if channel.name != new_name:
            await channel.edit(name=new_name)
            print(f"[{ts()}] Channel → {new_name}")
    except discord.Forbidden:
        print("ERROR: Missing 'Manage Channels' permission.")
    except Exception as e:
        print(f"[{ts()}] Channel rename error: {e}")

@tasks.loop(seconds=UPDATE_INTERVAL)
async def auto_status_post():
    """Delete the old status embed and post a fresh one every 30 seconds."""
    global last_status_message
    if STATUS_CHANNEL_ID == 0:
        return
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return

    info  = await get_server_info()
    embed = build_embed(info)

    # Delete the previous message if it exists
    if last_status_message:
        try:
            await last_status_message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass  # Already deleted or no permission, move on
        last_status_message = None

    # Post the new one
    try:
        last_status_message = await channel.send(embed=embed)
        print(f"[{ts()}] Status posted → {info.get('players', '?')}/{info.get('max_players', '?')} players")
    except discord.Forbidden:
        print("ERROR: Bot can't send messages in STATUS_CHANNEL_ID — check permissions.")
    except Exception as e:
        print(f"[{ts()}] Auto-post error: {e}")

# ── PREFIX COMMAND — !sendplayercount (Admins only) ───────────────────────────
@bot.command(name="sendplayercount")
@commands.has_permissions(administrator=True)
async def sendplayercount(ctx):
    """Manually trigger a fresh status post. Deletes the old one. Admins only."""
    global last_status_message
    async with ctx.typing():
        info  = await get_server_info()
        embed = build_embed(info)

    # Delete old auto-post if it exists
    if last_status_message:
        try:
            await last_status_message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        last_status_message = None

    # Delete the admin's command message to keep channel clean
    try:
        await ctx.message.delete()
    except (discord.NotFound, discord.Forbidden):
        pass

    last_status_message = await ctx.send(embed=embed)

@sendplayercount.error
async def sendplayercount_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You need **Administrator** permissions to use this command.", delete_after=5)
    else:
        await ctx.send(f"❌ Something went wrong: {error}", delete_after=5)

# ── SLASH COMMAND — /server ───────────────────────────────────────────────────
@tree.command(name="server", description="Show the Arma Reforger RP server status")
async def server_command(interaction: discord.Interaction):
    await interaction.response.defer()
    info  = await get_server_info()
    embed = build_embed(info)
    await interaction.followup.send(embed=embed)

# ── EVENTS ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅  Bot online: {bot.user} ({bot.user.id})")
    print(f"📡  BattleMetrics Server ID: {SERVER_ID}")
    print(f"🔄  Update interval: {UPDATE_INTERVAL}s")
    if STATUS_CHANNEL_ID != 0:
        print(f"📢  Auto-posting to channel: {STATUS_CHANNEL_ID}")
    try:
        synced = await tree.sync()
        print(f"⚡  Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Sync error: {e}")
    update_presence.start()
    update_channel_name.start()
    auto_status_post.start()

# ── RUN ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if "YOUR" in DISCORD_TOKEN or "YOUR" in BATTLEMETRICS_TOKEN or "YOUR" in SERVER_ID:
        print("❌  Fill in DISCORD_TOKEN, BATTLEMETRICS_TOKEN, SERVER_ID, and RP_SERVER_NAME in the config!")
    else:
        bot.run(DISCORD_TOKEN)

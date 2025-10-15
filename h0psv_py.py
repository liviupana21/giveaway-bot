import discord
from discord.ext import commands
import asyncio
import datetime
import random
import os
import threading
from flask import Flask

# ================= CONFIG =================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GIVEAWAY_CHANNEL_ID = int(os.environ.get("GIVEAWAY_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= FLASK HEALTH SERVER =================

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running", 200

@app.route("/health")
def health():
    status = {
        "bot_online": bot.is_ready(),
        "guilds": len(bot.guilds),
        "latency_ms": round(bot.latency * 1000) if bot.is_ready() else None
    }
    return status, 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# pornește Flask într-un thread separat
threading.Thread(target=run_flask, daemon=True).start()

# ================= STATE =================

active_giveaways = {}  # {message_id: end_time}

# ================= UI COMPONENTS =================

class GiveawayMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.select = discord.ui.Select(
            placeholder="Alege o acțiune...",
            options=[
                discord.SelectOption(label="Start Giveaway", value="start", emoji="🎉"),
                discord.SelectOption(label="End Giveaway", value="end", emoji="🛑")
            ]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        selected = self.select.values[0]
        if selected == "start":
            await interaction.response.send_modal(GiveawayModal())
        elif selected == "end":
            await end_giveaway(interaction)

class GiveawayModal(discord.ui.Modal, title="Start Giveaway"):
    prize = discord.ui.TextInput(label="Premiu", placeholder="Ex: Discord Nitro", required=True)
    duration = discord.ui.TextInput(label="Durată (secunde)", placeholder="Ex: 60", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            duration_int = int(self.duration.value)
            if duration_int <= 0:
                return
            await start_giveaway(interaction, self.prize.value, duration_int)
        except Exception:
            return

# ================= GIVEAWAY LOGIC =================

async def start_giveaway(interaction: discord.Interaction, prize: str, duration: int):
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY ACTIV 🎉",
        description=f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {duration} secunde",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Pornit de {interaction.user.name}")

    msg = await interaction.channel.send(embed=embed)
    try:
        await msg.add_reaction("🎉")
    except discord.Forbidden:
        pass

    active_giveaways[msg.id] = end_time

    while True:
        time_left = int((end_time - datetime.datetime.utcnow()).total_seconds())
        if time_left <= 0:
            break
        embed.description = (
            f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\n"
            f"Timp rămas: {time_left} secunde"
        )
        try:
            await msg.edit(embed=embed)
        except discord.NotFound:
            active_giveaways.pop(msg.id, None)
            return
        await asyncio.sleep(1)

    active_giveaways.pop(msg.id, None)

    # Reîncarcă mesajul pentru reacții
    reaction = None
    for attempt in range(3):
        await asyncio.sleep(1)
        try:
            msg = await interaction.channel.fetch_message(msg.id)
        except discord.NotFound:
            return
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        if reaction:
            break

    if not reaction:
        end_embed = discord.Embed(
            title="🚫 Giveaway încheiat",
            description="Nicio reacție detectată. Giveaway-ul a fost anulat.",
            color=discord.Color.red()
        )
        return await safe_edit_message(msg, end_embed)

    try:
        users = [user async for user in reaction.users() if not user.bot]
    except discord.Forbidden:
        users = []

    if not users:
        end_embed = discord.Embed(
            title="⚠️ Giveaway încheiat",
            description="Nimeni nu a participat la giveaway.",
            color=discord.Color.orange()
        )
        return await safe_edit_message(msg, end_embed)

    winner = random.choice(users)
    end_embed = discord.Embed(
        title="🎉 Giveaway încheiat",
        description=f"Felicitări pentru câștigător:\n{winner.mention}",
        color=discord.Color.green()
    )
    end_embed.set_footer(text=f"Premiu: {prize}")
    await safe_edit_message(msg, end_embed)

async def safe_edit_message(msg: discord.Message, embed: discord.Embed):
    try:
        await msg.edit(embed=embed)
    except (discord.NotFound, discord.Forbidden):
        return

async def end_giveaway(interaction: discord.Interaction):
    for msg_id, _ in list(active_giveaways.items()):
        try:
            msg = await interaction.channel.fetch_message(msg_id)
        except discord.NotFound:
            active_giveaways.pop(msg_id, None)
            continue

        try:
            await msg.delete()
            active_giveaways.pop(msg_id, None)
            if not interaction.response.is_done():
                await interaction.response.send_message("🛑 Giveaway-ul a fost oprit și mesajul a fost șters.", ephemeral=True)
            else:
                await interaction.followup.send("🛑 Giveaway-ul a fost oprit și mesajul a fost șters.", ephemeral=True)
            return
        except discord.Forbidden:
            return

# ================= MONITORIZARE MENIU =================

async def ensure_menu_exists():
    await bot.wait_until_ready()
    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)

    if not channel:
        print("❌ Canalul de giveaway nu a fost găsit.")
        return

    while not bot.is_closed():
        found = False
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.content.startswith("🎁 Meniu Giveaway:"):
                found = True
                break

        if not found:
            try:
                await channel.send("🎁 Meniu Giveaway:", view=GiveawayMenu())
                print("🔁 Meniul de giveaway a fost refăcut.")
            except Exception:
                pass

        await asyncio.sleep(3600)

# ================= EVENTS =================

@bot.event
async def on_ready():
    print(f"{bot.user} este online!")

    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if channel:
        exists = False
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.content.startswith("🎁 Meniu Giveaway:"):
                exists = True
                break
        if not exists:
            try:
                await channel.send("🎁 Meniu Giveaway:", view=GiveawayMenu())
            except Exception:
                pass
    else:
        print("❌ Canalul de giveaway nu a fost găsit.")

    bot.loop.create_task(ensure_menu_exists())

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot:
        return

    end_time = active_giveaways.get(reaction.message.id)
    if not end_time:
        return

    if datetime.datetime.utcnow() > end_time:
        try:
            await reaction.remove(user)
            try:
                await user.send("⏰ Giveaway-ul s-a terminat și nu mai poți participa.")
            except discord.Forbidden:
                pass
        except discord.Forbidden:
            pass

# ================= RUN =================

bot.run(DISCORD_TOKEN)

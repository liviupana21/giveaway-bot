import discord
from discord.ext import commands
import asyncio
import datetime
import random
import os

# ================= CONFIG =================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GIVEAWAY_CHANNEL_ID = int(os.environ.get("GIVEAWAY_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

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
    prize = discord.ui.TextInput(label="Premiu", placeholder="Ex: Discord Nitro")
    duration = discord.ui.TextInput(label="Durată (secunde)", placeholder="Ex: 60")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration_int = int(self.duration.value)
        except ValueError:
            await interaction.response.send_message("⛔ Durata trebuie să fie un număr!", ephemeral=True)
            return

        await start_giveaway(interaction, self.prize.value, duration_int)

        await interaction.response.send_message(
            f"✅ Giveaway-ul pentru **{self.prize.value}** a fost creat cu succes!",
            ephemeral=True
        )

# ================= GIVEAWAY LOGIC =================

async def start_giveaway(interaction, prize, duration):
    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY ACTIV 🎉",
        description=f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {duration} secunde",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Pornit de {interaction.user.name}")

    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("🎉")

    active_giveaways[msg.id] = end_time

    while True:
        time_left = int((end_time - datetime.datetime.utcnow()).total_seconds())
        if time_left <= 0:
            break
        embed.description = f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {time_left} secunde"
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

    active_giveaways.pop(msg.id, None)

    await asyncio.sleep(1)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")

    if not reaction:
        embed = discord.Embed(
            title="⛔ Giveaway încheiat",
            description="Nicio reacție detectată. Giveaway-ul a fost anulat.",
            color=discord.Color.red()
        )
        await msg.edit(embed=embed)
        return

    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        embed = discord.Embed(
            title="⚠️ Giveaway încheiat",
            description="Nimeni nu a participat la giveaway.",
            color=discord.Color.orange()
        )
        await msg.edit(embed=embed)
    else:
        winner = random.choice(users)
        embed = discord.Embed(
            title="🎉 Giveaway încheiat",
            description=f"Felicitări pentru câștigător:\n{winner.mention}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Premiu: {prize}")
        await msg.edit(embed=embed)

async def end_giveaway(interaction):
    for msg_id, end_time in list(active_giveaways.items()):
        try:
            msg = await interaction.channel.fetch_message(msg_id)
        except discord.NotFound:
            continue

        try:
            await msg.delete()
            active_giveaways.pop(msg_id, None)
            await interaction.response.send_message("🛑 Giveaway-ul a fost oprit și mesajul a fost șters.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("❌ Nu am permisiuni să șterg mesajul.", ephemeral=True)
            return

    await interaction.response.send_message("⚠️ Nu există niciun giveaway activ în acest canal.", ephemeral=True)

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
            await channel.send("🎁 Meniu Giveaway:", view=GiveawayMenu())
            print("🔁 Meniul de giveaway a fost refăcut.")

        await asyncio.sleep(3600)

# ================= EVENTS =================

@bot.event
async def on_ready():
    print(f"{bot.user} este online!")

    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if channel:
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.content.startswith("🎁 Meniu Giveaway:"):
                break
        else:
            await channel.send("🎁 Meniu Giveaway:", view=GiveawayMenu())

    bot.loop.create_task(ensure_menu_exists())

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    end_time = active_giveaways.get(reaction.message.id)
    if not end_time:
        return

    if datetime.datetime.utcnow() > end_time:
        try:
            await reaction.remove(user)
            await user.send("⏰ Giveaway-ul s-a terminat și nu mai poți participa.")
        except discord.Forbidden:
            pass

# ================= RUN =================

bot.run(DISCORD_TOKEN)

import discord
from discord.ext import commands
import asyncio
import datetime
import random
import os

# ================= CONFIG =================

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")  # Setează tokenul în variabilele de mediu
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STATE =================

active_giveaways = {}  # {message_id: end_time}

# ================= UI COMPONENTS =================

class GiveawayMenu(discord.ui.View):
    @discord.ui.select(
        placeholder="Alege o acțiune...",
        options=[
            discord.SelectOption(label="Start Giveaway", value="start", emoji="🎉"),
            discord.SelectOption(label="End Giveaway", value="end", emoji="🛑")
        ]
    )
    async def select_callback(self, select, interaction: discord.Interaction):
        if select.values[0] == "start":
            await interaction.response.send_modal(GiveawayModal())
        elif select.values[0] == "end":
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

    # Actualizare timp în timp real
    while True:
        time_left = int((end_time - datetime.datetime.utcnow()).total_seconds())
        if time_left <= 0:
            break
        embed.description = f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {time_left} secunde"
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

    active_giveaways.pop(msg.id, None)

    # Colectare participanți
    msg = await interaction.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")

    if not reaction:
        await interaction.channel.send("Nicio reacție detectată, giveaway anulat.")
        return

    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        await interaction.channel.send("Nimeni nu a participat la giveaway.")
    else:
        winner = random.choice(users)
        await interaction.channel.send(f"🎊 Felicitări {winner.mention}, ai câștigat **{prize}**!")

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

# ================= COMENZI =================

@bot.command()
async def menu(ctx):
    await ctx.send("🎁 Meniu Giveaway:", view=GiveawayMenu())

@bot.event
async def on_ready():
    print(f"{bot.user} este online!")

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

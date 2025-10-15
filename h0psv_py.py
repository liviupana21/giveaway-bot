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
intents.guilds = True
intents.members = True  # ajută la identificarea utilizatorilor (pentru DM/remove reacții)

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STATE =================

active_giveaways = {}  # {message_id: end_time}

# ================= UI COMPONENTS =================

class GiveawayMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # meniu nelimitat
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
        # Evităm "Something went wrong" cu defer + followup și tratăm excepțiile corect
        await interaction.response.defer(ephemeral=True)
        try:
            duration_int = int(self.duration.value)
            if duration_int <= 0:
                await interaction.followup.send("⛔ Durata trebuie să fie un număr pozitiv.", ephemeral=True)
                return

            await start_giveaway(interaction, self.prize.value, duration_int)

            await interaction.followup.send(
                f"✅ Giveaway-ul pentru **{self.prize.value}** a fost creat cu succes!",
                ephemeral=True
            )
        except ValueError:
            await interaction.followup.send("⛔ Durata trebuie să fie un număr!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Nu am permisiuni suficiente în acest canal.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ A apărut o eroare la pornirea giveaway-ului.", ephemeral=True)

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

    # Timer live
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
            # Mesajul a fost șters; încheiem giveaway-ul
            active_giveaways.pop(msg.id, None)
            return
        await asyncio.sleep(1)

    active_giveaways.pop(msg.id, None)

    # Asigură-te că reacțiile sunt vizibile și actualizate (retry cu re-fetch)
    reaction = None
    for attempt in range(3):
        await asyncio.sleep(1)
        # re-încarcă mesajul pentru a obține reacțiile actuale
        try:
            msg = await interaction.channel.fetch_message(msg.id)
        except discord.NotFound:
            # Dacă mesajul nu mai există, nu avem ce anunța
            return
        reaction = discord.utils.get(msg.reactions, emoji="🎉")
        if reaction:
            break

    # Construiește embed-ul final în funcție de rezultate
    if not reaction:
        end_embed = discord.Embed(
            title="⛔ Giveaway încheiat",
            description="Nicio reacție detectată. Giveaway-ul a fost anulat.",
            color=discord.Color.red()
        )
        await safe_edit_message(msg, end_embed)
        return

    # Listează utilizatorii (exclude boturile)
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
        await safe_edit_message(msg, end_embed)
        return

    winner = random.choice(users)
    end_embed = discord.Embed(
        title="🎉 Giveaway încheiat",
        description=f"Felicitări pentru câștigător:\n{winner.mention}",
        color=discord.Color.green()
    )
    end_embed.set_footer(text=f"Premiu: {prize}")
    await safe_edit_message(msg, end_embed)

async def safe_edit_message(msg: discord.Message, embed: discord.Embed):
    """Editează mesajul cu protecție la erori comune."""
    try:
        await msg.edit(embed=embed)
    except discord.NotFound:
        # mesaj șters între timp
        return
    except discord.Forbidden:
        # permisiuni insuficiente
        return

async def end_giveaway(interaction: discord.Interaction):
    # Oprește primul giveaway activ din canalul curent
    for msg_id, end_time in list(active_giveaways.items()):
        try:
            msg = await interaction.channel.fetch_message(msg_id)
        except discord.NotFound:
            # Dacă nu găsim mesajul, îl scoatem din registru
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
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Nu am permisiuni să șterg mesajul.", ephemeral=True)
            else:
                await interaction.followup.send("❌ Nu am permisiuni să șterg mesajul.", ephemeral=True)
            return

    if not interaction.response.is_done():
        await interaction.response.send_message("⚠️ Nu există niciun giveaway activ în acest canal.", ephemeral=True)
    else:
        await interaction.followup.send("⚠️ Nu există niciun giveaway activ în acest canal.", ephemeral=True)

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
            except discord.Forbidden:
                print("❌ Permisiuni insuficiente pentru a posta meniul.")
            except Exception:
                print("❌ Eroare la refacerea meniului.")

        await asyncio.sleep(3600)  # verifică la fiecare 1 oră

# ================= EVENTS =================

@bot.event
async def on_ready():
    print(f"{bot.user} este online!")

    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if channel:
        # Postează meniul doar dacă nu există deja
        exists = False
        async for message in channel.history(limit=50):
            if message.author == bot.user and message.content.startswith("🎁 Meniu Giveaway:"):
                exists = True
                break
        if not exists:
            try:
                await channel.send("🎁 Meniu Giveaway:", view=GiveawayMenu())
            except discord.Forbidden:
                print("❌ Permisiuni insuficiente pentru a posta meniul.")
    else:
        print("❌ Canalul de giveaway nu a fost găsit.")

    # Pornește monitorizarea periodică
    bot.loop.create_task(ensure_menu_exists())

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot:
        return

    # Permite doar reacții de participare pe giveaway-uri active
    end_time = active_giveaways.get(reaction.message.id)
    if not end_time:
        return

    # Dacă reacția e adăugată după expirare, o eliminăm
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

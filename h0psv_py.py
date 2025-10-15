import os
import discord
from discord.ext import commands
import asyncio
import random
import datetime

# ================= BOT CONFIG =================

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GIVEAWAY_CHANNEL_ID = int(os.environ.get('GIVEAWAY_CHANNEL_ID'))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dicționar pentru giveaway-uri active {message_id: end_time}
active_giveaways = {}

# ================= EVENTS =================

@bot.event
async def on_ready():
    print(f'{bot.user} este online!')

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

# ================= FUNCȚIE TIMER =================

async def update_giveaway_timer(msg, prize, end_time):
    while True:
        time_left = int((end_time - datetime.datetime.utcnow()).total_seconds())
        if time_left <= 0:
            break
        embed = msg.embeds[0]
        embed.description = f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {time_left} secunde"
        await msg.edit(embed=embed)
        await asyncio.sleep(1)

# ================= GIVEAWAY COMMAND =================

@bot.command()
async def giveaway(ctx, duration: int, *, prize: str):
    channel = bot.get_channel(GIVEAWAY_CHANNEL_ID)
    if not channel:
        await ctx.send("❌ Canalul de giveaway nu a fost găsit.")
        return

    end_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)

    embed = discord.Embed(
        title="🎉 GIVEAWAY! 🎉",
        description=f"Premiu: **{prize}**\nReacționează cu 🎉 pentru a participa!\nTimp rămas: {duration} secunde",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f'Pornit de {ctx.author.name}')

    msg = await channel.send(embed=embed)
    await msg.add_reaction("🎉")

    active_giveaways[msg.id] = end_time

    asyncio.create_task(update_giveaway_timer(msg, prize, end_time))

    await asyncio.sleep(duration)

    # Giveaway terminat
    active_giveaways.pop(msg.id)

    # Colectează participanții
    msg = await channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji="🎉")

    if not reaction:
        return await channel.send("Nicio reacție detectată, giveaway anulat.")

    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        await channel.send("Nimeni nu a participat la giveaway.")
    else:
        winner = random.choice(users)
        await channel.send(f"🎊 Felicitări {winner.mention}, ai câștigat **{prize}**!")

# ================= END =================

bot.run(DISCORD_TOKEN)

import discord
from discord.ext import commands
import asyncio
import random
import os


# ================= BOT CONFIG  =================

DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')
GIVEAWAY_CHANNEL_ID =  os.environ.get('GIVEAWAY_CHANNEL_ID')

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ================= GIVEAWAY COMMAND  =================

@bot.event
async def on_ready():
    print(f'{bot.user} este online!')

@bot.command()
async def giveaway(ctx, duration: int, *, prize: str):

    channel_id = int(os.getenv('GIVEAWAY_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)


    embed = discord.Embed(
        title = "🎉 Giveaway! 🎉",
        description = f"Premiu: **{prize}**\nReactioneaza cu 🎉 pentru a participa!\nTimp: {duration} secunde",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f'Pornit de {ctx.author.name}')
    msg = await channel.send(embed=embed)
    await msg.add_reaction("🎉")

    await asyncio.sleep(duration)

    msg = await ctx.channel.fetch_message(msg.id)
    reaction = discord.utils.get(msg.reactions, emoji = "🎉")

    if not reaction:
        return await ctx.send("Nicio reactie detectata, giveaway anulat.")
    
    users = [user async for user in reaction.users() if not user.bot]
    if not users:
        await ctx.send("Nimeni nu a participat la giveaway.")
    else:
        winner = random.choice(users)
        await ctx.send(f"Felicitari {winner.mention}, ai castigat **{prize}**!")

# ================= END GIVEAWAY COMMAND  =================

bot.run(DISCORD_TOKEN)

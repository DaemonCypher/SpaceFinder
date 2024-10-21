import discord
import random
import os, sys
from discord.ext import commands
#from casino import *
#from miniGames import *
from keep_alive import keep_alive

#line what charecter is needed to activate commands
client = commands.Bot(command_prefix='.')

@client.event
async def on_ready():
    print('Bot is ready.\nBot is online to wreck havoc!')

@client.event
async def on_member_join(member):
    print(f'{member} has joined a server.')

@client.event
async def on_member_remove(member):
    print(f'{member} has left a server.')

@client.command()
async def clear(ctx,amount=1):
    await ctx.channel.purge(limit=amount+1)

@client.command()
async def kick(ctx,member : discord.Member,*,reason=None):
    await member.kick(reason=reason)

@client.command()
async def ban(ctx,member : discord.Member,*,reason=None):
    await member.ban(reason=reason)
    
@client.command()
async def unban(ctx,*,memeber):
    banned_users= await ctx.guild.bans()
    member_name,member_discriminator= member.split('#')
    for ban_entry in banned_users:
        user = ban_entry.user
        if (user.name,user.discriminator)==(member_name,member_discriminator):
            await ctx.guild.unban(user)
            await ctx.send(f'Unbanned {user.mention}')
            return

@client.command()
async def who(ctx):
    await ctx.send('Your part of the CYPHER ARMY!')

@client.command()
async def load(ctx,extension):
    client.load_extension(f'cogs.{extension}')
    

@client.command()
async def unload(ctx,extension):
    client.unload_extension(f'cogs.{extension}')

for filename in os.listdir('./cogs'):
    if filename.endswith('.py'):
        client.load_extension(f'cogs.{filename[:-3]}')


    

        
keep_alive()
client.run('Token')

# -*- coding: utf-8 -*-
import discord
from discord.ext import commands
import os


class HelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__()

    async def send_bot_help(self, mapping):
        """Sends a list of modules"""
        embed = discord.Embed(color=bot.ColorDefault)
        embed.set_author(name=f"{bot.user.name}'s modules", icon_url=bot.user.avatar_url)
        for cog in mapping:
            if cog:
                embed.add_field(name=cog.qualified_name, value=f"`-help {cog.qualified_name}`", inline=True)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        """Sends a list of extension commands and a short description"""
        embed = discord.Embed(title=f"{cog.qualified_name} extension", color=bot.ColorDefault)
        for command in cog.get_commands():
            if not command.hidden:
                embed.add_field(name=f"`{command.brief}`", value=command.description, inline=False)
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        """Sends a detailed description of the command"""
        embed = discord.Embed(color=bot.ColorDefault)
        embed.add_field(name=f"Usage of {command.name} command:", value=f"`{bot.command_prefix}{command.brief}`")
        embed.set_footer(text="Enabled" if command.enabled else "Disabled")
        if command.usage:
            arguments = ''
            col_width = max(len(row[0]) for row in command.usage)
            for row in command.usage:
                arguments += f"`{'|'.join(word.rjust(col_width) for word in row[:-1])}` {row[2]}\n"
            embed.add_field(name=f"Arguments:", value=arguments, inline=False)
        await self.get_destination().send(embed=embed)

    async def send_error_message(self, error):
        """Sends an error message if command doesn't exist"""
        embed = discord.Embed(title="Something went wrong", description=f"🚫 Nothing found", color=bot.ColorError)
        await self.get_destination().send(embed=embed)


token = os.environ['TOKEN']
prefix = os.environ['COMMAND_PREFIX']
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix=prefix, help_command=HelpCommand(), case_insensitive=True, intents=intents)

bot.ColorDefault = int(os.environ['COLOR_DEFAULT'], base=16)
bot.ColorError = int(os.environ['COLOR_ERROR'], base=16)
bot.BannedGuildInvite = os.environ['BANNED_GUILD_INVITE']
bot.HomeworkID = int(os.environ['HOMEWORK_CATEGORY_ID'])
bot.ScheduleID = int(os.environ['SCHEDULE_CHANNEL_ID'])
bot.ScheduleURL = os.environ['SCHEDULE_URL']


@bot.event
async def on_ready():
    """Is called when the bot has finished logging in and setting things up"""
    await bot.change_presence(activity=discord.Game("Real Live"))
    print(f"{bot.user.name}(ID:{bot.user.id}) online with prefix: {prefix}")


@bot.event
async def on_command_error(ctx, error):
    """Sends an error message to the context channel"""
    if hasattr(ctx.command, 'on_error'):
        return

    error = getattr(error, 'original', error)
    ignored = (
        commands.CommandNotFound,
    )
    embed = discord.Embed(title="Something went wrong", description="🚫 ", color=bot.ColorError)

    if isinstance(error, ignored):
        return

    if isinstance(error, discord.NotFound):
        embed.description += f"Unknown {error.text.split()[1].lower()}"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.MissingRequiredArgument):
        embed.description += f"**{error.param.name}** is a required argument that is missing"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.BadArgument):
        embed.description += error.args[0].replace('"', '**')
        return await ctx.send(embed=embed)

    if isinstance(error, commands.MemberNotFound):
        embed.description += f"Member **{error.argument}** not found"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.UserNotFound):
        embed.description += f"User **{error.argument}** not found"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.DisabledCommand):
        embed.description += f"**{error.args[0].split()[0]}** command is disabled"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.CommandOnCooldown):
        embed.description += f"Calm down! Retry in **{error.retry_after:.2f}**s"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.MissingRole):
        embed.description += f"Role **{error.missing_role}** is required to run this command"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.MissingPermissions):
        embed.description += f"You don't have permission to run this command"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.ExtensionNotFound):
        embed.description += f"Module **{error.name[5:]}** does not exist"
        return await ctx.send(embed=embed)

    if isinstance(error, commands.NotOwner):
        embed.description += f"You do not own this bot"
        return await ctx.send(embed=embed)

    raise error


@bot.event
async def on_member_join(member: discord.Member):
    """Sends a greeting when someone joins a server or informs the guild owner about the absence of a system channel"""
    if member.guild.system_channel:
        await member.guild.system_channel.send(f"{member.mention} has **joined** a server")
    else:
        await member.guild.owner.send("I haven't find the system channel, You can specify it in the server settings")


@bot.event
async def on_member_remove(member: discord.Member):
    """Informs that the user has removed from the server (Including ban/kick)"""
    if member.guild.system_channel:
        await member.guild.system_channel.send(f"{member.mention} has **left** a server")

for filename in os.listdir('./cogs'):
    if filename.endswith('.py'):
        bot.load_extension(f'cogs.{filename[:-3]}')

bot.run(token)

# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
from os import listdir


class Settings(commands.Cog):
    """
    Allows to change the Bot's functionality directly from the channel.
    Only responds to a request from a owner.
    Inherits from commands.Cog
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="toggle_module",
        brief="toggle_module [extension]",
        usage=[
            ["extension", "required", "Extension name"],
        ],
        description="Turns a module on/off",
        hidden=True
    )
    @commands.is_owner()
    async def toggle_module(self, ctx, extension: str):
        """Turns a module on/off

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param extension: str - Extension name
        """
        try:
            self.bot.load_extension(f'cogs.{extension}')
            embed = discord.Embed(description=f"**{extension.capitalize()}** was loaded", color=self.bot.ColorDefault)
            print("test1")
        except commands.ExtensionAlreadyLoaded:
            print("test2")
            self.bot.unload_extension(f'cogs.{extension}')
            embed = discord.Embed(description=f"**{extension.capitalize()}** was unloaded", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="reload",
        brief="reload [extension]",
        usage=[
            ["extension", "required", "Can be used 'all' or fill empty"]
        ],
        description="Reloads an extension (applies code changes)",
        hidden=True
    )
    @commands.is_owner()
    async def reload(self, ctx, extension: str = "all"):
        """Reloads a cog (applies code changes)

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param extension: str - Extension name
        """
        if extension == 'all':
            for filename in listdir('./cogs'):
                if filename.endswith('.py'):
                    self.bot.reload_extension(f'cogs.{filename[:-3]}')
        else:
            self.bot.reload_extension(f'cogs.{extension}')
        embed = discord.Embed(color=self.bot.ColorDefault)
        embed.description = f"**{extension.capitalize()}** module(s) was updated"
        await ctx.send(embed=embed)

    @commands.command(
        name="toggle",
        brief="toggle [command]",
        usage=[
            ["command", "required", "Just a command"]
        ],
        description="Turns command on/off"
    )
    @commands.has_permissions(administrator=True)
    async def toggle(self, ctx, command):
        """Turns command on/off

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param command: str - Command object to toggle (error if this command, will be changed to commands.Command)
        """
        command = self.bot.get_command(command)
        if command == ctx.command:
            embed = discord.Embed(title="Something went wrong", color=self.bot.ColorError)
            embed.description = "🚫That's not good idea"
        else:
            command.enabled = not command.enabled
            ternary = "Enabled" if command.enabled else "Disabled"
            embed = discord.Embed(description=f"{ternary} **{command.qualified_name}**", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Settings(bot))

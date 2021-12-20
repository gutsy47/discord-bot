# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import psycopg2
from urllib.parse import urlparse
import os


class Settings(commands.Cog, name="settings"):
    """Configuring bot functionality"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Postgres connection
        result = urlparse(os.environ['DATABASE_URL'])
        with psycopg2.connect(
                dbname=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
        ) as connection:
            connection.autocommit = True
            self.cursor = connection.cursor()

    @commands.command(
        name="toggle_greetings",
        brief="Turns on/off notification system for member join/remove in the system channel",
        help="If enabled, the bot will send messages about adding/removing a user to the system channel",
        usage=[]
    )
    @commands.has_permissions(administrator=True)
    async def toggle_greetings(self, ctx):
        # Update database
        self.cursor.execute("SELECT is_greetings FROM guild WHERE guild_id=%s;", (ctx.guild.id,))
        is_greetings = not self.cursor.fetchone()[0]
        self.cursor.execute("UPDATE guild SET is_greetings=%s WHERE guild_id=%s;", (is_greetings, ctx.guild.id))

        # Send message
        answer = '' if is_greetings else '**not**'
        embed = discord.Embed(description=f"Now I'll {answer} take care of greetings", color=self.bot.ColorDefault)
        if not ctx.guild.system_channel:
            embed.set_footer(text="Set the system channel in the server settings so that I can do it")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Settings(bot))

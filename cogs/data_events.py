# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import psycopg2
import os


class DataEvents(commands.Cog):
    """Allows to change Bot's functionality directly from discord. Only responds to request from owner"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Postgres connection
        with psycopg2.connect(
                dbname=os.environ['DATABASE_NAME'],
                user=os.environ['DATABASE_USER'],
                password=os.environ['DATABASE_PASSWORD']
        ) as self.connection:
            self.connection.autocommit = True
            self.cursor = self.connection.cursor()


def setup(bot):
    bot.add_cog(DataEvents(bot))

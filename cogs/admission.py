# -*- coding: utf-8 -*-

from discord.ext import commands


class Admission(commands.Cog, name="admission"):
    """Updating the lists of applicants"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Admission(bot))

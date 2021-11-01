# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import gspread
import os
import asyncio


class English(commands.Cog):
    """Helps to learn a set of new english words"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        credentials = {
            "type": "service_account",
            "project_id": os.environ['GOOGLE_PROJECT_ID'],
            "private_key_id": os.environ["GOOGLE_PRIVATE_KEY_ID"],
            "private_key": os.environ["GOOGLE_PRIVATE_KEY"].replace('\\n', '\n'),
            "client_email": os.environ["GOOGLE_CLIENT_EMAIL"],
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ['GOOGLE_CLIENT_X509_CERT_URL']
        }
        service_account = gspread.service_account_from_dict(credentials)
        self.spreadsheet = service_account.open("Word lists")
        self.users = {}

    @commands.command(
        name="select",
        brief="select",
        description="Displays a list of dictionaries, waiting for your choice"
    )
    @commands.dm_only()
    async def select(self, ctx):
        """Loads word lists from the database, displays them and processes the user's reaction"""
        embed = discord.Embed(title="Word lists", description="Loading...", color=self.bot.ColorDefault)
        message = await ctx.send(embed=embed)

        # Get worksheet object from opened spreadsheet (With progress bar)
        words = {}
        for worksheet in self.spreadsheet.worksheets():
            embed.description = embed.description + '.' if embed.description != "Loading..." else "Loading"
            await message.edit(embed=embed)  # Loading rate
            words[worksheet.title] = worksheet.get_all_values()

        # Send word lists
        embed.description = ''
        embed.set_footer(text="Press the button corresponding to the block number")
        for key, value in words.items():
            value = '\n'.join([f"{pair[0]} – {pair[1]}" for pair in value[:4]]) + "\n..."
            embed.add_field(name=f"List {key}", value=f"```{value}```", inline=True)
        await message.edit(embed=embed)

        # Add reactions
        reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        for i in range(len(words)):
            await message.add_reaction(emoji=reactions[i])  # Words should be sorted by title and length should be <= 10

        # Wait for user's reaction
        def check(reaction, user):
            return user != self.bot.user and str(reaction.emoji) in reactions

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.exceptions.TimeoutError:
            embed = discord.Embed(title="Time out", color=self.bot.ColorDefault)
            await message.edit(embed=embed)
        else:
            index = str(reactions.index(reaction.emoji) + 1)
            embed = discord.Embed(
                title=f"You've selected block number {index}",
                description="Use **-help English** if you don't know commands for further interaction",
                color=self.bot.ColorDefault
            )
            await ctx.send(embed=embed)
            self.users[user.id] = words[index]


def setup(bot):
    bot.add_cog(English(bot))

# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import gspread
import os
import asyncio
from random import randint


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
        self.users_tmp = {}

    @commands.command(
        name="select",
        brief="select",
        description="Displays a list of dictionaries, waiting for your choice"
    )
    @commands.dm_only()
    async def select(self, ctx):
        """Loads word lists from the database, displays them and processes the user's reaction

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        """
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
            value = '\n'.join([f"{pair[0]} – {pair[1]}" for pair in value[:4]]) + ("\n..." if len(value) > 4 else '')
            embed.add_field(name=f"List {key}", value=f"```{value}```", inline=False)
        await message.edit(embed=embed)

        # Add reactions
        reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        for i in range(len(words)):
            await message.add_reaction(emoji=reactions[i])  # Words should be sorted by title and length should be <= 10

        # Wait for user's reaction
        try:
            def check(reaction, user):
                return user != self.bot.user and str(reaction.emoji) in reactions

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

    @commands.command(
        name="learn",
        brief="learn (word list number)",
        usage=[
            ["number", "optional", "Word list number (integer)"]
        ],
        description="Launches training in test format"
    )
    @commands.dm_only()
    async def learn(self, ctx, index: int = None):
        """Launches a multi-choice learning system

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param index: int - Number of the list of words to get it from the DB
        """
        # Get word_list as user_tmp
        if index:
            try:
                worksheet = self.spreadsheet.worksheet(title=str(index))
                self.users[ctx.author.id] = worksheet.get_all_values()
            except gspread.exceptions.WorksheetNotFound:
                raise commands.BadArgument("Block with this number does not exist")
        try:
            self.users_tmp[ctx.author.id] = self.users[ctx.author.id][:]
        except KeyError:
            raise commands.BadArgument("You haven't selected a block yet")

        # Main function
        while True:
            # Prepare data
            index = randint(0, len(self.users_tmp[ctx.author.id]) - 1)
            word = self.users_tmp[ctx.author.id].pop(index)
            choice = ['', '', '', '']
            correct = randint(0, 3)
            choice[correct] = word
            for i in range(4):
                if not choice[i]:
                    while True:
                        index = randint(0, len(self.users[ctx.author.id]) - 1)
                        choice[i] = self.users[ctx.author.id][index]
                        if choice[i] != word:
                            break

            # Send a choice message
            embed = discord.Embed(title=word[1].capitalize(), description='', color=self.bot.ColorDefault)
            answers = ['a', 'b', 'c', 'd', 'exit']
            for i in range(4):
                embed.description += f"`{answers[i]}` - {choice[i][0]}\n"
            embed.set_footer(text="Enter 'exit' to end the cycle early")
            message = await ctx.send(embed=embed)

            # Wait for user's answer
            try:
                def check(msg):
                    return msg.channel == ctx.channel and msg.content.lower() in answers

                answer = await self.bot.wait_for('message', timeout=60.0, check=check)
                answer = answers.index(answer.content.lower())
            except asyncio.exceptions.TimeoutError:
                embed.description = "Time out"
                await message.edit(embed=embed)
                return
            else:
                if answer == 4:  # Exit
                    return
                embed.title = '🟢 ' if answer == correct else '🔴 '
                embed.title += ' - '.join(word[::-1]).capitalize()
                await message.edit(embed=embed)

            # The words ended. Repeat?
            if len(self.users_tmp[ctx.author.id]) == 0:
                # Send message
                embed = discord.Embed(title="Words ended", description="Repeat?", color=self.bot.ColorDefault)
                message = await ctx.send(embed=embed)
                for button in ('🟩', '🟥'):
                    await message.add_reaction(emoji=button)

                # Wait for user's reaction
                try:
                    def check(reaction, user):
                        emoji = str(reaction.emoji)
                        channel = reaction.message.channel
                        return channel == ctx.channel and user != self.bot.user and emoji in ('🟩', '🟥')

                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.exceptions.TimeoutError:
                    embed.description = "Time out"
                    return await message.edit(embed=embed)
                else:
                    if reaction.emoji == '🟩':
                        self.users_tmp[ctx.author.id] = self.users[ctx.author.id][:]
                    else:
                        return

    @commands.command(
        name="exam",
        brief="exam (word list number)",
        usage=[
            ["number", "optional", "Word list number (integer)"]
        ],
        description="Launches exam"
    )
    @commands.dm_only()
    async def exam(self, ctx, index: int = None):
        """Launches an exam system

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param index: int - Number of the list of words to get it from the DB
        """
        # Get word_list as user_tmp
        if index:
            try:
                worksheet = self.spreadsheet.worksheet(title=str(index))
                self.users[ctx.author.id] = worksheet.get_all_values()
            except gspread.exceptions.WorksheetNotFound:
                raise commands.BadArgument("Block with this number does not exist")
        try:
            self.users_tmp[ctx.author.id] = self.users[ctx.author.id][:]
        except KeyError:
            raise commands.BadArgument("You haven't selected a block yet")

        # Main function
        wrong_answers = []
        while True:
            # Prepare data & send a message
            index = randint(0, len(self.users_tmp[ctx.author.id]) - 1)
            word = self.users_tmp[ctx.author.id].pop(index)
            embed = discord.Embed(title=word[1].capitalize(), color=self.bot.ColorDefault)
            embed.set_footer(text="Enter 'exit' to end the cycle early")
            message = await ctx.send(embed=embed)

            # Wait for user's answer
            try:
                def check(msg):
                    return msg.channel == ctx.channel and msg.author != self.bot.user

                answer = await self.bot.wait_for('message', timeout=60.0, check=check)
            except asyncio.exceptions.TimeoutError:
                embed.description = "Time out"
                await message.edit(embed=embed)
                return
            else:
                if answer.content.lower() == "exit":
                    self.users_tmp[ctx.author.id] = []
                else:
                    translated = ' - '.join(word[::-1]).capitalize()
                    if answer.content.lower() == word[0].lower():
                        embed.title = '🟢 ' + translated
                    else:
                        embed.title = '🔴 ' + translated
                        wrong_answers.append(f"{translated} (Your answer: **{answer.content}**)")
                    await message.edit(embed=embed)

            # The words ended. Repeat?
            if len(self.users_tmp[ctx.author.id]) == 0:
                # Send message
                accuracy = 100 - round(len(wrong_answers) / len(self.users[ctx.author.id]) * 100)
                embed = discord.Embed(
                    title=f"That's all. Your accuracy is {accuracy}%",
                    description="Wrong answers:" if accuracy != 100 else '',
                    color=self.bot.ColorDefault
                )
                for item in wrong_answers:
                    embed.description += f"\n{item}"
                return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(English(bot))

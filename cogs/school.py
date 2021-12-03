# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import os
import requests
import bs4
from bs4 import BeautifulSoup
import psycopg2
from urllib.parse import urlparse


class School(commands.Cog):
    """A module for interacting with homework and schedule"""
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

    @staticmethod
    async def date_format(date: datetime):
        """Returns str(date) formatted to AA DD.MM.YY"""
        week = {
            'Mon': 'понедельник', 'Tue': 'вторник', 'Wed': 'среда', 'Thu': 'четверг', 'Fri': 'пятница',
            'Sat': 'суббота', 'Sun': 'воскресенье'
        }
        return week[datetime.strftime(date, '%a')].capitalize() + datetime.strftime(date, ' %d.%m.%y')

    async def get_homework(self, guild: int, date: datetime):
        """Returns homework for a given date

        :param guild: int - Guild's ID
        :param date: datetime - DateTime object
        :return: dict - {lesson: {content: str, files: list, source: str}, }
        """
        # Get channels with homework from DB
        self.cursor.execute(
            "SELECT channel_id, lesson_name FROM channel WHERE guild_id=%s AND lesson_name IS NOT NULL;", (guild, )
        )
        selected = self.cursor.fetchall()

        # Main loop
        homework = {}
        for channel_id, lesson in selected:
            channel = self.bot.get_channel(channel_id)
            async for message in channel.history():
                if "дз" in message.content and datetime.strftime(date, '%d.%m.%y') in message.content:
                    content = ''
                    if '\n' in message.content:
                        content = message.content[message.content.find('\n'):]  # Cut off the title
                    files = [file.url for file in message.attachments]
                    src = message.jump_url
                    homework[lesson.capitalize()] = {'content': content, 'files': files, 'source': src}
                    break

        return homework

    async def get_schedule(self, date: datetime):
        """Returns the timetable from the school website

        :param date: datetime - The date for which you need to get the schedule
        :return: dict - {course: [lesson1, lesson2], } or commands.BadArgument
        """
        # Argument error handler
        if date.weekday() > 4:
            return commands.BadArgument("No lessons on weekends")
        today = datetime.today()
        if (date.month not in [today.month, today.month + 1]) or (date.year != today.year):
            return commands.BadArgument("Schedule not posted for the selected date")

        # Get soup
        response = requests.get(self.bot.ScheduleURL)
        soup = BeautifulSoup(response.text, 'lxml')

        # Get dates
        dates = [h2.get_text().split()[-2] for h2 in soup.find_all('h2') if "Расписание" in h2.get_text()]
        if str(date.day) not in dates:
            return commands.BadArgument("Schedule not posted for the selected date")

        # Get schedules in HTML format for date
        tables = soup.find_all('tbody')
        pos = dates.index(str(date.day))
        tables = [tables[pos*2], tables[pos*2 + 1]]

        # Get schedule in dict format from tables
        schedule = {}
        for table in tables:
            new_table = []
            for row in table:  # Create table with replaced colspans
                if isinstance(row, bs4.element.Tag):  # There are NavigableStrings in rows
                    new_row = []
                    for col in row:
                        if isinstance(col, bs4.element.Tag):  # There are NavigableStrings in cols
                            new_row.append(col.get_text().replace('\n', '').replace('\xa0', ''))
                            if 'colspan' in col.attrs:  # Replace all cols with colspan
                                for _ in range(int(col.attrs['colspan']) - 1):
                                    new_row.append(col.get_text().replace('\n', '').replace('\xa0', ''))
                    new_table.append(new_row)
            new_table = [[new_table[j][i] for j in range(len(new_table))] for i in range(len(new_table[0]))]  # rot90
            for row in new_table[1:]:
                schedule[row[0]] = [lesson.capitalize() for lesson in row[2:]]

        return schedule

    @commands.Cog.listener()
    async def on_ready(self):
        self.homework_and_schedule.start()

    @tasks.loop(minutes=15)
    async def homework_and_schedule(self):
        """Schedule distribution
        Sends timetable and homework for all guilds to the schedule channel.
        """
        # Get distribution channels from DB
        self.cursor.execute("SELECT channel_id FROM channel WHERE is_schedule=True;")
        channel_ids = self.cursor.fetchall()
        channels = [self.bot.get_channel(channel_id[0]) for channel_id in channel_ids]  # discord.Channel objects

        # Get tomorrow date (or monday if tomorrow is weekend)
        date = datetime.today() + timedelta(days=1)
        if date.weekday() > 4:
            date += timedelta(days=7 - date.weekday())

        # Get schedule data
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            return

        # Main loop
        for channel in channels:
            # Avoid existing message
            async for message in channel.history(limit=None):
                try:
                    if datetime.strftime(date, '%d.%m.%y') in message.embeds[0].title:
                        return
                except (TypeError, IndexError):  # Not schedule message
                    continue

            # Get homework
            homework = await self.get_homework(guild=channel.guild.id, date=date)

            # Message create
            title = await self.date_format(date=date)
            embed = discord.Embed(title=title, description='', url=self.bot.ScheduleURL, color=self.bot.ColorDefault)
            for index, lesson in enumerate(timetable['11м']):  # Schedule
                embed.description += f"\n`{index + 1}` {lesson}" if lesson.strip() else ''
            for lesson, hw in homework.items():  # Homework
                if lesson[:3].lower() in embed.description.lower():
                    value = hw['content']
                    if hw['files']:
                        value += "\nПрикреплённые файлы: "
                        for index, link in enumerate(hw['files']):
                            value += f"[№{index + 1}]({link})"
                            value += ', ' if index + 1 < len(hw['files']) else ''
                    embed.add_field(name=lesson, value=value, inline=False)
            embed.url = self.bot.ScheduleURL

            # Send message and add refresh button
            message = await channel.send(embed=embed)
            await message.add_reaction(emoji='🔄')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Updates homework in reaction message

        :param payload: discord.RawReactionActionEvent - The raw event payload data
        """
        # Get payload data
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:  # Avoiding DM messages
            return
        message = await channel.fetch_message(payload.message_id)
        member = payload.member
        reaction = payload.emoji

        # Get schedule channels from DB
        self.cursor.execute("SELECT channel_id FROM channel WHERE is_schedule=True;")
        selected = self.cursor.fetchall()
        channels = [channel_id[0] for channel_id in selected]

        # Work only with schedule channels, avoiding bot's reactions
        if channel.id not in channels:
            return
        if member == self.bot.user:
            return
        if reaction.name != '🔄':
            return await message.remove_reaction(emoji=reaction, member=member)

        # Get message embed without homework (fields)
        embed = message.embeds[0]
        date = datetime.strptime(embed.title.split()[1], '%d.%m.%y')
        embed.clear_fields()

        # Update homework
        homework = await self.get_homework(guild=channel.guild.id, date=date)
        for lesson, hw in homework.items():
            if lesson[:3].lower() in embed.description.lower():
                value = hw['content']
                if hw['files']:
                    value += "\nПрикреплённые файлы: "
                    for index, link in enumerate(hw['files']):
                        value += f"[№{index + 1}]({link})"
                        value += ', ' if index + 1 < len(hw['files']) else ''
                embed.add_field(name=lesson, value=value, inline=False)

        # Edit message and update DB
        await message.edit(embed=embed)
        await message.remove_reaction(emoji=reaction, member=member)

    @commands.command(
        name="set_course",
        brief="set_course [course]",
        usage=[
            ["course", "required", "Course name as it written in the schedule (e.g. '11м')"]
        ],
        description="Set course name to your guild"
    )
    async def set_course(self, ctx, course: str):
        """Sets course_name in channel table

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param course: str - Course name (e.g. '11м')
        """
        # Update DB
        try:
            self.cursor.execute("UPDATE guild SET course_name=%s WHERE guild_id=%s;", (course, ctx.guild.id))
        except psycopg2.errors.ForeignKeyViolation:
            raise commands.BadArgument("Name is incorrect")

        # Send message
        embed = discord.Embed(description=f"Course of this server is set as **{course}**", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="toggle_schedule",
        brief="toggle_schedule [channel]",
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"]
        ],
        description="Set or unset channel to which schedule'll be sent"
    )
    async def toggle_schedule(self, ctx, channel: discord.TextChannel):
        """Sets channel to which schedule'll be sent

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        """
        # Get channel ID or None
        self.cursor.execute("SELECT channel_id FROM channel WHERE is_schedule AND guild_id=%s;", (channel.guild.id, ))
        current_id = self.cursor.fetchone()

        # Change state
        message = f"Now the schedule will be sent to {channel.mention}"
        if not current_id:  # First setup
            self.cursor.execute("UPDATE channel SET is_schedule=True WHERE channel_id=%s;", (channel.id, ))
        elif current_id[0] != channel.id:  # Change channel
            self.cursor.execute("UPDATE channel SET is_schedule=False WHERE channel_id=%s;", (current_id[0], ))
            self.cursor.execute("UPDATE channel SET is_schedule=True WHERE channel_id=%s;", (channel.id, ))
        else:  # Delete distribution
            message = "Now the schedule will not be sent"
            self.cursor.execute("UPDATE channel SET is_schedule=False WHERE channel_id=%s;", (channel.id, ))

        # Send message
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="set_lesson",
        brief="set_lesson [channel] (lesson_name)",
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"],
            ["lesson_name", "optional", "Lesson name or nothing if you want to unset"]
        ],
        description="Set lesson name for the channel from where homework will be collected"
    )
    async def set_lesson(self, ctx, channel: discord.TextChannel, lesson: str):
        """Sets channel from which homework'll be received

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        :param lesson: str - Lesson name according to the course table
        """
        # Change state
        lesson = lesson.lower()
        message = f"Now I will look for **{lesson}** homework In the **{channel.mention}**"
        try:
            self.cursor.execute("UPDATE channel SET lesson_name=%s WHERE channel_id=%s;", (lesson, channel.id))
        except psycopg2.errors.ForeignKeyViolation:
            raise commands.BadArgument("Name is incorrect\nFind out the list of available lessons using `get_lessons`")

        # Send message
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="unset_lesson",
        brief="unset_lesson [channel]",
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"],
        ],
        description="Stop collecting homework from channel"
    )
    async def unset_lesson(self, ctx, channel: discord.TextChannel):
        """Removes channel homework from DB

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        """
        self.cursor.execute("UPDATE channel SET lesson_name=NULL WHERE channel_id=%s;", (channel.id, ))
        message = f"Now the **{channel.mention}** is not related to homework"
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="get_lessons",
        brief="get_lessons",
        usage=[],
        description="Sends a list of all available lessons"
    )
    async def get_lessons(self, ctx):
        """Sends a list of all available lessons from DB"""
        self.cursor.execute("SELECT lesson_name FROM lesson;")
        lessons = [lesson[0].capitalize() for lesson in self.cursor.fetchall()]
        embed = discord.Embed(title="Available lessons", description='\n'.join(lessons), color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="schedule",
        brief="schedule [course] (date)",
        usage=[
            ["course", "required", "Format as on school website"],
            ["date", "optional", "DD.MM.YY (default: today)"]
        ],
        description="Sends schedule"
    )
    async def schedule(self, ctx, course: str, date: str = None):
        """Sends schedule for class

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param course: str - Course name in format as on the school website
        :param date: str - Date in DD.MM.YY format (today as default)
        """
        # Argument error handler
        self.cursor.execute("SELECT course_name FROM course")
        courses = [course[0] for course in self.cursor.fetchall()]
        if course not in courses:
            raise commands.BadArgument("Incorrect course")
        try:
            date = datetime.strptime(date, '%d.%m.%y') if date else datetime.today()
        except ValueError:
            raise commands.BadArgument("**Date** should have **DD.MM.YY** format")

        # Get data
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            raise timetable

        # Create message
        title = await self.date_format(date=date) + ' ' + course
        embed = discord.Embed(title=title, description='', color=self.bot.ColorDefault)
        for index, lesson in enumerate(timetable[course]):
            embed.description += f"\n`{index + 1}` {lesson}" if lesson else ''

        # Send message
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(School(bot))

# -*- coding: utf-8 -*-

import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import os
import requests
import bs4
from bs4 import BeautifulSoup
import psycopg2
from urllib.parse import urlparse


class School(commands.Cog, name="school"):
    """Functionality for students (schedule, homework, etc.)"""
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
        return week[date.strftime('%a')].capitalize() + date.strftime(' %d.%m.%y')

    async def get_homework(self, guild_id: int, date1: datetime, date2: datetime = None):
        """Returns homework from guild in date range

        :param guild_id: int - Guild's ID
        :param date1: datetime - Start date (one day can be specified)
        :param date2: datetime - End date (None as default)
        :return: dict - {date: {lesson: {content: str, files: [str], source: str}}
        """
        # Date handler
        date2 = date2 or date1
        date_range = [(date1 + timedelta(days=x)).strftime('%d.%m.%y') for x in range(0, (date2 - date1).days + 1)]

        # Get channels with homework from DB
        self.cursor.execute(
            "SELECT channel_id, lesson_name FROM ds_channel WHERE guild_id=%s AND lesson_name IS NOT NULL;", (guild_id,)
        )
        selected = self.cursor.fetchall()

        # Main loop
        homework = {date: {} for date in date_range}
        for channel_id, lesson in selected:
            channel = self.bot.get_channel(channel_id)
            async for message in channel.history():
                if "дз" in message.content.lower():
                    try:
                        current = message.content[3:11]
                        datetime.strptime(current, '%d.%m.%y')
                    except ValueError:
                        continue
                    if current in date_range:
                        homework[current][lesson.capitalize()] = {
                            'content': message.content[message.content.find('\n'):] if '\n' in message.content else '',
                            'files': [file.url for file in message.attachments],
                            'source': message.jump_url
                        }
                    elif datetime.strptime(current, '%d.%m.%y') < datetime.strptime(date_range[0], '%d.%m.%y'):
                        break

        return homework

    async def get_schedule(self, date: datetime):
        """Returns the timetable from the school website

        :param date: datetime - The date for which you need to get the schedule
        :return: dict - {course: [lesson1, lesson2]} or RuntimeError
        """
        # Argument error handler
        if date.weekday() > 4:
            return RuntimeError("No lessons on weekends")
        today = datetime.today()
        if (date.month not in [today.month, today.month + 1]) or (date.year != today.year):
            return RuntimeError("Schedule not posted for the selected date")

        # Get soup
        response = requests.get(self.bot.ScheduleURL)
        soup = BeautifulSoup(response.text, 'lxml')

        # Get dates
        dates = [h2.get_text().split()[-2] for h2 in soup.find_all('h2') if "Расписание" in h2.get_text()]
        if str(date.day) not in dates:
            return RuntimeError("Schedule not posted for the selected date")

        # Get schedules in HTML format for date
        tables = [table for table in soup.find_all('tbody') if table.get_text().strip() != '']
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
                schedule[row[0]] = [lesson.capitalize() for lesson in row[1:]]

        return schedule

    @tasks.loop(minutes=15)
    async def schedule_distribution(self):
        """Schedule distribution
        Sends timetable and homework for all guilds to the schedule channel.
        """
        # Get distribution channels from DB
        self.cursor.execute(
            "SELECT channel_id, course_name FROM ds_channel "
            "INNER JOIN ds_guild ON ds_guild.guild_id=ds_channel.guild_id "
            "WHERE is_schedule=True;"
        )
        result = [{'channel': self.bot.get_channel(row[0]), 'course': row[1]} for row in self.cursor.fetchall()]

        # Get tomorrow date (or monday if tomorrow is weekend)
        date = datetime.today() + timedelta(days=1)
        if date.weekday() > 4:
            date += timedelta(days=7 - date.weekday())

        # Get schedule data
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            return

        # Main loop
        for row in result:
            # Message create
            embed = discord.Embed(
                title=await self.date_format(date=date),
                description='',
                url=self.bot.ScheduleURL,
                color=self.bot.ColorDefault
            )

            # Add schedule to description
            for index, lesson in enumerate(timetable[row['course']]):
                embed.description += f"\n`{index + 1}` {lesson.strip()}" if lesson.strip() else ''

            async for message in row['channel'].history(limit=None):
                try:
                    # Avoiding existing message
                    if "Дома" not in message.embeds[0].title and date.strftime('%d.%m.%y') in message.embeds[0].title:
                        if '\n' + message.embeds[0].description == embed.description:
                            break
                        await message.delete()
                except (TypeError, IndexError):  # Not schedule message
                    continue
            else:
                # Get homework
                homework = await self.get_homework(guild_id=row['channel'].guild.id, date1=date)

                # Add homework to fields
                for lesson, hw in homework[date.strftime('%d.%m.%y')].items():
                    value = hw['content']
                    if hw['files']:
                        value += "\nПрикреплённые файлы: "
                        for index, link in enumerate(hw['files']):
                            value += f"[№{index + 1}]({link})"
                            value += ', ' if index + 1 < len(hw['files']) else ''
                    if value:
                        embed.add_field(name=lesson, value=value, inline=False)
                embed.url = self.bot.ScheduleURL

                # Send message and add refresh button
                message = await row['channel'].send(embed=embed)
                await message.add_reaction(emoji='🔄')

    @tasks.loop(hours=12)
    async def weekly_homework_distribution(self):
        """Weekly homework distribution
        Sends homework for week every friday
        """
        # Is friday check
        if datetime.today().weekday() != 4:
            return

        # Get start and end date
        date1 = datetime.today() + timedelta(days=3)
        date2 = date1 + timedelta(days=4)

        # Get distribution channels from DB
        self.cursor.execute("SELECT channel_id FROM ds_channel WHERE is_schedule=True;")
        channel_ids = self.cursor.fetchall()
        channels = [self.bot.get_channel(channel_id[0]) for channel_id in channel_ids]  # discord.Channel objects

        # Message title
        title = f"Домашнее задание с {date1.strftime('%d.%m.%y')} по {date2.strftime('%d.%m.%y')}"

        # Main loop
        for channel in channels:
            async for message in channel.history(limit=None):
                try:
                    # Avoid existing message
                    if title == message.embeds[0].title:
                        break
                except (TypeError, IndexError):  # Not schedule message
                    continue
            else:
                # Get homework
                homework = await self.get_homework(guild_id=channel.guild.id, date1=date1, date2=date2)

                # Create message
                embed = discord.Embed(title=title, color=self.bot.ColorDefault)

                # Add homework to fields
                for date, homework in homework.items():
                    values = ''
                    for lesson, hw in homework.items():
                        value = hw['content']
                        if hw['files']:
                            value += "\nПрикреплённые файлы: "
                            for index, link in enumerate(hw['files']):
                                value += f"[№{index + 1}]({link})"
                                value += ', ' if index + 1 < len(hw['files']) else ''
                        if value:
                            values += f'**{lesson}**{value}\n'
                    embed.add_field(name=date, value=values or r'¯\_(ツ)_/¯ Ничего не задано')

                # Send message and add refresh button
                message = await channel.send(embed=embed)
                await message.add_reaction(emoji='🔄')

    @commands.Cog.listener()
    async def on_ready(self):
        self.schedule_distribution.start()
        self.weekly_homework_distribution.start()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Updates homework in reaction message

        :param payload: discord.RawReactionActionEvent - The raw event payload data
        """
        # Get payload data
        channel = self.bot.get_channel(payload.channel_id)
        if not channel:  # Avoid DM messages
            return
        message = await channel.fetch_message(payload.message_id)
        member = payload.member
        reaction = payload.emoji

        # Get schedule channels from DB
        self.cursor.execute("SELECT channel_id FROM ds_channel WHERE is_schedule=True;")
        selected = self.cursor.fetchall()
        channels = [channel_id[0] for channel_id in selected]

        # Work only with schedule channels, avoiding bot's reactions
        if channel.id not in channels:  # Non-schedule channel
            return
        if member == self.bot.user:  # Bot's reaction
            return
        if reaction.name != '🔄':  # Another reactions
            return await message.remove_reaction(emoji=reaction, member=member)

        # Loading indicator
        async def loading_indicator(msg: discord.Message):
            """Refresh the loading indicator (footer) every 0.5 sec"""
            indicator = "Loading"
            while True:
                indicator = indicator + '.' if indicator != "Loading..." else "Loading"
                await msg.edit(embed=msg.embeds[0].set_footer(text=indicator))
                await asyncio.sleep(0.5)
        task = self.bot.loop.create_task(loading_indicator(msg=message))

        # Main
        if "Домашнее задание" in message.embeds[0].title:  # Weekly homework
            embed = discord.Embed(title=message.embeds[0].title, color=self.bot.ColorDefault)

            # Get start and end date
            date1 = datetime.strptime(embed.title.split()[3], '%d.%m.%y')
            date2 = datetime.strptime(embed.title.split()[5], '%d.%m.%y')

            # Get homework
            homework = await self.get_homework(guild_id=channel.guild.id, date1=date1, date2=date2)

            # Create message
            for date, homework in homework.items():
                values = ''
                for lesson, hw in homework.items():
                    value = hw['content']
                    if hw['files']:
                        value += "\nПрикреплённые файлы: "
                        for index, link in enumerate(hw['files']):
                            value += f"[№{index + 1}]({link})"
                            value += ', ' if index + 1 < len(hw['files']) else ''
                    if value:
                        values += f'**{lesson}**{value}\n'
                embed.add_field(name=date, value=values or r'¯\_(ツ)_/¯ Ничего не задано')
        else:  # Schedule
            embed = discord.Embed(
                title=message.embeds[0].title,
                description=message.embeds[0].description,
                url=self.bot.ScheduleURL,
                color=self.bot.ColorDefault
            )

            # Date from title
            date = datetime.strptime(embed.title.split()[1], '%d.%m.%y')

            # Get homework
            homework = await self.get_homework(guild_id=channel.guild.id, date1=date)

            # Create message
            for lesson, hw in homework[date.strftime('%d.%m.%y')].items():
                value = hw['content']
                if hw['files']:
                    value += "\nПрикреплённые файлы: "
                    for index, link in enumerate(hw['files']):
                        value += f"[№{index + 1}]({link})"
                        value += ', ' if index + 1 < len(hw['files']) else ''
                embed.add_field(name=lesson, value=value, inline=False)

        # Edit message and remove reaction
        task.cancel()  # Stop loading indicator
        await message.edit(embed=embed)
        await message.remove_reaction(emoji=reaction, member=member)

    @commands.command(
        name="schedule",
        brief="Send schedule by date and course",
        help=(
                "Receives the timetable from the school website, "
                "selects the specified class and sends the timetable to the channel where the command was called."
                "\nIf the server has a specified course, then it can be not specified in command arguments."
        ),
        usage=[
            ["date", "optional", "DD.MM.YY (default: today)"],
            ["course", "optional", "Course in format as on school website"]
        ]
    )
    async def schedule(self, ctx, date: str = None, course: str = None):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param date: str - Date in DD.MM.YY format (today as default)
        :param course: str - Course name in format as on the school website
        """
        # Course argument
        if course:
            self.cursor.execute("SELECT course_name FROM course")
            courses = [course[0] for course in self.cursor.fetchall()]
            if course not in courses:
                raise commands.BadArgument("Incorrect course")
        else:
            self.cursor.execute("SELECT course_name FROM ds_guild WHERE guild_id=%s", (ctx.guild.id, ))
            course = self.cursor.fetchone()
            if not course:
                raise commands.BadArgument("**Course** not specified in this server. Use **set_course** command")
            course = course[0]

        # Date argument
        try:
            date = datetime.strptime(date, '%d.%m.%y') if date else datetime.today()
            if date.weekday() > 4:
                date += timedelta(days=7 - date.weekday())
        except ValueError:
            raise commands.BadArgument("**Date** should have **DD.MM.YY** format")

        # Get schedule
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            raise commands.BadArgument(timetable.__str__())

        # Create message
        title = await self.date_format(date=date) + ' ' + course
        embed = discord.Embed(title=title, description='', color=self.bot.ColorDefault)
        for index, lesson in enumerate(timetable[course]):
            embed.description += f"\n`{index + 1}` {lesson}" if lesson else ''

        # Send message
        await ctx.send(embed=embed)

    @commands.command(
        name="set_course",
        brief="Set course name to your server",
        help=(
                "Bot remembers the specified class and will send out the schedule and homework "
                "if a channels for sending schedule and collecting homework are specified."
        ),
        usage=[
            ["course", "required", "Course in format as on school website (e.g. '11м')"]
        ]
    )
    async def set_course(self, ctx, course: str):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param course: str - Course name (e.g. '11м')
        """
        # Update DB
        try:
            self.cursor.execute("UPDATE ds_guild SET course_name=%s WHERE guild_id=%s;", (course, ctx.guild.id))
        except psycopg2.errors.ForeignKeyViolation:
            raise commands.BadArgument("Name is incorrect")

        # Send message
        embed = discord.Embed(description=f"Course of this server is set as **{course}**", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="toggle_schedule",
        brief="Set channel to which schedule'll be sent",
        help=(
                "Sets/changes/removes the specified channel as a broadcast channel. "
                "For correct operation, the course must be specified, "
                "you can also specify the channels from which you want to collect tasks."
        ),
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"]
        ]
    )
    async def toggle_schedule(self, ctx, channel: discord.TextChannel):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        """
        # Get channel ID or None
        self.cursor.execute("SELECT channel_id FROM ds_channel WHERE is_schedule AND guild_id=%s;", (channel.guild.id, ))
        current_id = self.cursor.fetchone()

        # Change state
        message = f"Now the schedule will be sent to {channel.mention}"
        if not current_id:  # First setup
            self.cursor.execute("UPDATE ds_channel SET is_schedule=True WHERE channel_id=%s;", (channel.id, ))
        elif current_id[0] != channel.id:  # Change channel
            self.cursor.execute("UPDATE ds_channel SET is_schedule=False WHERE channel_id=%s;", (current_id[0], ))
            self.cursor.execute("UPDATE ds_channel SET is_schedule=True WHERE channel_id=%s;", (channel.id, ))
        else:  # Delete distribution
            message = "Now the schedule will not be sent"
            self.cursor.execute("UPDATE ds_channel SET is_schedule=False WHERE channel_id=%s;", (channel.id, ))

        # Send message
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="set_lesson",
        brief="Set lesson name for the channel from where homework will be collected",
        help=(
                "Sets the specified channel as the channel from which homework will be retrieved. "
                "The task message must have this format:"
                "```\nдз {день недели} {дата в формате ДД.ММ.ГГ}"
                "\nТекст сообщения```"
                "You can also attach files."
        ),
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"],
            ["lesson_name", "optional", "Lesson name or nothing if you want to unset"]
        ]
    )
    async def set_lesson(self, ctx, channel: discord.TextChannel, lesson: str):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        :param lesson: str - Lesson name according to the course table
        """
        # Change state
        lesson = lesson.lower()
        message = f"Now I will look for **{lesson}** homework In the **{channel.mention}**"
        try:
            self.cursor.execute("UPDATE ds_channel SET lesson_name=%s WHERE channel_id=%s;", (lesson, channel.id))
        except psycopg2.errors.ForeignKeyViolation:
            raise commands.BadArgument("Name is incorrect\nFind out the list of available lessons using `get_lessons`")

        # Send message
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="unset_lesson",
        brief="Return the usual properties for the channel",
        help=(
                "Returns the usual properties for the channel. "
                "Messages from here will no longer be checked for the **дз** keyword"
        ),
        usage=[
            ["channel", "required", "Channel mention (use '#channel-name' or ID)"]
        ]
    )
    async def unset_lesson(self, ctx, channel: discord.TextChannel):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param channel: discord.TextChannel - Channel mention or ID
        """
        self.cursor.execute("UPDATE ds_channel SET lesson_name=NULL WHERE channel_id=%s;", (channel.id, ))
        message = f"Now the **{channel.mention}** is not related to homework"
        embed = discord.Embed(description=message, color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="get_lessons",
        brief="Send a list of all available lessons",
        help=(
                "Returns a list of all lessons reviewed by the administrator. "
                "If the list is missing something, write **gutsy#9100** (Bot owner)"
        ),
        usage=[]
    )
    async def get_lessons(self, ctx):
        self.cursor.execute("SELECT lesson_name FROM lesson;")
        lessons = [lesson[0].capitalize() for lesson in self.cursor.fetchall()]
        embed = discord.Embed(title="Available lessons", description='\n'.join(lessons), color=self.bot.ColorDefault)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(School(bot))

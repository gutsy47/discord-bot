# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import gspread
import os
import requests
import bs4
from bs4 import BeautifulSoup


class School(commands.Cog):
    """A module for interacting with homework and schedule"""
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
        self.spreadsheet = service_account.open("Schedules")

    @staticmethod
    async def date_format(date: datetime):
        """Returns str(date) formatted to AA DD.MM.YY"""
        week = {
            'Mon': 'понедельник', 'Tue': 'вторник', 'Wed': 'среда', 'Thu': 'четверг', 'Fri': 'пятница',
            'Sat': 'суббота', 'Sun': 'воскресенье'
        }
        return week[datetime.strftime(date, '%a')].capitalize() + datetime.strftime(date, ' %d.%m.%y')

    async def update_db(self, date: datetime, schedule: dict = None, homework: dict = None, format: bool = False):
        """Sends data to google sheets. Formats if specified

        :param date: datetime - DateTime object, sheet names is dates
        :param schedule: dict - Schedule with the same style as in get_schedule (or None)
        :param homework: dict - Homework with the same style as in get_homework (or None)
        :param format: bool - Boolean value indicating the need to update the table style
        """
        # Get worksheet object from opened spreadsheet
        date = datetime.strftime(date, '%d.%m.%y')
        try:
            worksheet = self.spreadsheet.add_worksheet(title=date, rows='25', cols='11')
        except gspread.exceptions.APIError:
            worksheet = self.spreadsheet.worksheet(title=date)

        # Update schedule
        if schedule:
            worksheet.update('A1:K1', [['Course', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])  # Header
            worksheet.update('A2:K17', [[key] + value for key, value in schedule.items()])  # Content

        # Update homework
        if homework:
            worksheet.update('A18:D18', [['Name', 'Content', 'Files', 'Source']])  # Header
            rows = []
            for key, value in homework.items():
                homework[key]['content'] = homework[key]['content'].replace('\n', '\\n')
                homework[key]['files'] = ', '.join(homework[key]['files'])
                rows.append([key] + list(value.values()))
            worksheet.update('A19:D25', rows)  # Content

        # Set worksheet style
        if format:
            worksheet.format('A1:K25', {'wrapStrategy': 'CLIP'})  # Wrapping style for the whole table
            for cords in ('B2:K17', 'B19:D25'):  # Contents' borders
                worksheet.format(cords, {
                    'textFormat': {'fontSize': 9},
                    'borders': {
                        'top': {'style': 'SOLID'}, 'bottom': {'style': 'SOLID'},
                        'left': {'style': 'SOLID'}, 'right': {'style': 'SOLID'}
                    }
                })
            for cords in ('A1:K1', 'A18:D18', 'A1:A25'):  # Headers' borders
                worksheet.format(cords, {
                    'borders': {
                        'top': {'style': 'SOLID', 'width': 2}, 'bottom': {'style': 'SOLID', 'width': 2},
                        'left': {'style': 'SOLID', 'width': 2}, 'right': {'style': 'SOLID', 'width': 2}
                    },
                    'horizontalAlignment': 'RIGHT',
                    'textFormat': {'bold': True}
                })
            for cords in ('A1:K1', 'A18:D18'):  # Top headers' text style
                worksheet.format(cords, {'horizontalAlignment': 'CENTER', 'textFormat': {'fontSize': 12}})

    async def get_homework(self, date: datetime):
        """Returns homework for a given date

        :param date: datetime - DateTime object
        :return: dict - {lesson: {content: str, files: list, source: str}, }
        """
        lessons = {
            '📙physics': 'Физика', '📙maths': 'Математика', '📙ict': 'Информатика',
            '📗russian': 'Русский', '📗english': 'Английский',
            '📕literature': 'Литература', '📕history': 'История',
            '📘biology': 'Биология', '📘chemistry': 'Химия',
            '📒astronomy': 'Астрономия', '📒geography': 'География',
        }
        homework = {}
        for channel in self.bot.get_channel(self.bot.HomeworkID).text_channels:
            async for message in channel.history():
                if "дз" in message.content and datetime.strftime(date, '%d.%m.%y') in message.content:
                    lesson = lessons[str(message.channel)]
                    content = ''
                    if '\n' in message.content:
                        content = message.content[message.content.find('\n'):]  # Cut off the title
                    files = [file.url for file in message.attachments]
                    src = message.jump_url
                    homework[lesson] = {'content': content, 'files': files, 'source': src}
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
        Sends timetable and homework for the 11m course to the #Schedule channel.
        """
        channel = self.bot.get_channel(self.bot.ScheduleID)  # Schedule channel

        # Get tomorrow date (or monday if tomorrow is weekend)
        date = datetime.today() + timedelta(days=1)
        if date.weekday() > 4:
            date += timedelta(days=7 - date.weekday())

        # Avoid existing message
        async for message in channel.history(limit=None):  # Avoid existing messages
            if datetime.strftime(date, '%d.%m.%y') in message.embeds[0].title:
                return

        # Get data
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            return
        homework = await self.get_homework(date=date)

        # Message create
        title = await self.date_format(date=date)
        embed = discord.Embed(title=title, description='', url=self.bot.ScheduleURL, color=self.bot.ColorDefault)
        for index, lesson in enumerate(timetable['11м']):
            embed.description += f"\n`{index + 1}` {lesson}" if lesson.strip() else ''
        for lesson, hw in homework.items():
            if lesson[:3].lower() in embed.description.lower():
                value = hw['content']
                if hw['files']:
                    value += "\nПрикреплённые файлы: "
                    for index, link in enumerate(hw['files']):
                        value += f"[№{index + 1}]({link})"
                        value += ', ' if index + 1 < len(hw['files']) else ''
                embed.add_field(name=lesson, value=value, inline=False)
        embed.url = self.bot.ScheduleURL

        # Send message and update DB
        message = await channel.send(embed=embed)
        await message.add_reaction(emoji='🔄')
        await self.update_db(date=date, schedule=timetable, homework=homework, format=True)

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

        # Work only with #Schedule, avoiding bot's reactions
        if channel.id != self.bot.ScheduleID:
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
        homework = await self.get_homework(date=date)
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
        await self.update_db(date=date, homework=homework)

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
        courses = ('5а', '5б', '6а', '6б', '7а', '7б', '8а', '8б', '9а', '9б', '10м', '10х', '10э', '11м', '11х', '11э')
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

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(School(bot))

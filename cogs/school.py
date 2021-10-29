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
    """
    A module for interacting with homework, schedule, etc.
    Inherits from command.Cog
    """
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
        return week[datetime.strftime(date, '%a')] + datetime.strftime(date, ' %d.%m.%y')

    async def update_db(self, date: datetime, schedule: dict = None, homework: list = None, format: bool = False):
        """Sends data to google sheets. Formats if specified

        :param date: datetime - DateTime object, sheet names is dates
        :param schedule: dict - Schedule with the same style as in get_schedule.return (or None)
        :param homework: list - Homework with the same style as in get_homework.return (or None)
        :param format: bool - Boolean value indicating the need to update the table style
        """
        # Get worksheet object from opened spreadsheet
        date = datetime.strftime(date, '%d.%m.%y')
        try:
            worksheet = self.spreadsheet.add_worksheet(title=date, rows='25', cols='10')
        except gspread.exceptions.APIError:
            worksheet = self.spreadsheet.worksheet(title=date)

        # Update schedule
        if schedule:
            worksheet.update('A1:J1', [['Course', 1, 2, 3, 4, 5, 6, 7, 8, 9]])  # Header
            worksheet.update('A2:J17', [[key] + value for key, value in schedule.items()])  # Content

        # Update homework
        if homework:
            worksheet.update('A18:D18', [['Name', 'Content', 'Files', 'Source']])  # Header
            rows = []
            for item in homework:
                item['content'] = item['content'].replace('\n', '\\n')
                item['files'] = ', '.join(item['files'])
                rows.append(list(item.values()))
            worksheet.update('A19:D25', rows)  # Content

        # Set worksheet style
        if format:
            worksheet.format('A1:J25', {'wrapStrategy': 'CLIP'})  # Wrapping style for the whole table
            for cords in ('B2:J17', 'B19:D25'):  # Contents' borders
                worksheet.format(cords, {
                    'textFormat': {'fontSize': 9},
                    'borders': {
                        'top': {'style': 'SOLID'},
                        'bottom': {'style': 'SOLID'},
                        'left': {'style': 'SOLID'},
                        'right': {'style': 'SOLID'}
                    }
                })
            for cords in ('A1:J1', 'A18:D18', 'A1:A25'):  # Headers' borders
                worksheet.format(cords, {
                    'borders': {
                        'top': {'style': 'SOLID', 'width': 2},
                        'bottom': {'style': 'SOLID', 'width': 2},
                        'left': {'style': 'SOLID', 'width': 2},
                        'right': {'style': 'SOLID', 'width': 2}
                    },
                    'horizontalAlignment': 'RIGHT',
                    'textFormat': {'bold': True}
                })
            for cords in ('A1:J1', 'A18:D18'):  # Top headers' text style
                worksheet.format(cords, {'horizontalAlignment': 'CENTER', 'textFormat': {'fontSize': 12}})

    async def download_db(self, date: datetime, table: bool = False, hw: bool = False):
        """Returns homework from google sheets

        :param date: datetime - DateTime object, sheet names is dates
        :param table: bool - Boolean value indicating the need to download homework
        :param hw: bool - Boolean value indicating the need to download homework
        :return: schedule for course, homework or one of this
        """
        # Get worksheet object from opened spreadsheet
        worksheet = self.spreadsheet.worksheet(datetime.strftime(date, '%d.%m.%y'))

        # Schedule data
        schedule = {}
        if table:
            for row_number in range(2, 18):
                values = worksheet.row_values(row_number)
                schedule[values[0]] = values[1:]
            if not hw:
                return schedule

        # Homework data
        homework = []
        if hw:
            for row_number in range(19, 26):
                try:
                    values = worksheet.row_values(row_number)
                except IndexError:
                    continue
                values[1] = values[1].replace('\\n', '\n')
                values[2] = values[2].split(', ')
                homework.append({key: values[i] for i, key in enumerate(['name', 'content', 'files', 'source'])})
            if not table:
                return homework

        # Returns both
        if table and hw:
            return schedule, homework

    async def get_homework(self, date: datetime):
        """Returns homework for a given date

        :param date: datetime - DateTime object
        :return: dict - [{name: str, content: str, files: list, source: str}, ]
        """
        lessons = {
            '📙physics': 'Физика', '📙maths': 'Математика', '📙ict': 'Информатика',
            '📗russian': 'Русский', '📗english': 'Английский',
            '📕literature': 'Литература', '📕history': 'История',
            '📘biology': 'Биология', '📘chemistry': 'Химия',
            '📒astronomy': 'Астрономия', '📒geography': 'География',
        }
        homework = []
        for channel in self.bot.get_channel(self.bot.HomeworkID).text_channels:
            async for message in channel.history():
                if "дз" in message.content and datetime.strftime(date, '%d.%m.%y') in message.content:
                    name = lessons[str(message.channel)]
                    content = ''
                    if '\n' in message.content:
                        content = message.content[message.content.find('\n'):]  # Cut off the title
                    files = [file.url for file in message.attachments]
                    src = message.jump_url
                    homework.append({'name': name, 'content': content, 'files': files, 'source': src})
                    break
        if not homework:
            homework.append({'name': "Ничего не задано", 'content': r"¯\_(ツ)_/¯", 'files': [], 'source': ''})

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
        Sends timetable for the 11m course to the #Schedule channel.
        Also adds buttons(reactions) to view homework or hide data
        """
        channel = self.bot.get_channel(self.bot.ScheduleID)  # Schedule channel

        # Get tomorrow date (or monday if tomorrow is weekend)
        date = datetime.today() + timedelta(days=1)
        if date.weekday() > 4:
            date += timedelta(days=7 - date.weekday())

        # Avoid existing message
        last_message = await channel.fetch_message(channel.last_message_id)
        if datetime.strftime(date, '%d.%m.%y') in last_message.embeds[0].title:
            return

        # Get data
        timetable = await self.get_schedule(date=date)
        if not isinstance(timetable, dict):
            return

        # Message create
        formatted_date = await self.date_format(date=date)
        embed = discord.Embed(title=f"Расписание {formatted_date}", description='', color=self.bot.ColorDefault)
        for index, lesson in enumerate(timetable['11м']):
            embed.description += f"\n`{index + 1}` {lesson}" if lesson else ''

        # Send message and update DB
        message = await channel.send(embed=embed)
        await message.add_reaction(emoji='➡️')
        await self.update_db(date=date, schedule=timetable, homework=await self.get_homework(date=date), format=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Changes the schedule to homework and on the contrary. Clicking the up arrow hides the content

        :param payload: discord.RawReactionActionEvent - The raw event payload data
        """
        message: discord.Message = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        reaction: discord.Reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name)
        member: discord.Member = payload.member
        try:
            title = message.embeds[0].title.split()
            current = title[0] + ' '
            if current not in ("Расписание ", "ДЗ "):
                return
            file_name = '.'.join(title[2].split('.')[::-1]) + ' ' + title[1]
            date = ' '.join(title[1:])
        except IndexError:
            return
        except AttributeError:
            return

        if member == self.bot.user:
            return
        if (not reaction.me or reaction.count > 1) and message.author.id == self.bot.user.id:
            if reaction.emoji != '🔄':
                await reaction.remove(member)

        if reaction.emoji == '🔄':  # Recheck for new hw
            with open(f"schedules/{file_name}.json", 'r', encoding='UTF-8') as file:
                recheck = json.load(file)

            homework = await self.get_homework(date=date[-8:])
            recheck['homework'] = []
            if homework:
                for lesson in homework:
                    if lessons[lesson['lesson']][:3] in recheck['schedule']['description']:
                        value = lesson['content'] + f" ([Источник]({lesson['source']}))"
                        if lesson['attachments']:
                            value += "\nПрикреплённые файлы: "
                            for index, link in enumerate(lesson['attachments']):
                                value += f"[№{index + 1}]({link})"
                                value += ', ' if index + 1 < len(lesson['attachments']) else ''
                        recheck['homework'].append({'name': lessons[lesson['lesson']], 'value': value})
            else:
                recheck['homework'].append({'name': "Ничего не задано", 'value': r"¯\_(ツ)_/¯"})

            with open(f"schedules/{file_name}.json", 'w', encoding='UTF-8') as file:
                json.dump(recheck, file, ensure_ascii=False, indent=2)

            embed = discord.Embed(title=current + date, color=self.bot.ColorDefault)
            for lesson in recheck['homework']:
                embed.add_field(name=lesson['name'], value=lesson['value'], inline=False)
            await message.edit(embed=embed)
            await reaction.remove(member)

        elif reaction.emoji == '➡️':  # Change homework/schedule
            with open(f"schedules/{file_name}.json", 'r', encoding='UTF-8') as file:
                loaded = json.load(file)

            change = "ДЗ " if current == "Расписание " else "Расписание "
            embed = discord.Embed(title=change+date, color=self.bot.ColorDefault)
            if change == "ДЗ ":
                for lesson in loaded['homework']:
                    embed.add_field(name=lesson['name'], value=lesson['value'], inline=False)
                    await message.add_reaction(emoji='🔄')
            else:
                embed.description = loaded['schedule']['description']
                await message.remove_reaction(emoji='🔄', member=self.bot.user)

            await message.edit(embed=embed)

        elif reaction.emoji == '🔼':  # Hide
            embed = discord.Embed(title=current+date, color=self.bot.ColorDefault)

            await message.edit(embed=embed)
            for button in ('➡️', '🔼', '🔄'):
                await message.remove_reaction(emoji=button, member=self.bot.user)
            await message.add_reaction(emoji='🔽')

        elif reaction.emoji == '🔽':  # Show
            with open(f"schedules/{file_name}.json", 'r', encoding='UTF-8') as file:
                loaded = json.load(file)

            embed = discord.Embed(title=current+date, color=self.bot.ColorDefault)
            if current == "ДЗ ":
                for lesson in loaded['homework']:
                    embed.add_field(name=lesson['name'], value=lesson['value'], inline=False)
            else:
                embed.description = loaded['schedule']['description']

            await message.edit(embed=embed)
            await message.remove_reaction(emoji='🔽', member=self.bot.user)
            for button in ('🔼', '➡️'):
                await message.add_reaction(emoji=button)
            if current == "ДЗ ":
                await message.add_reaction(emoji='🔄')

    @commands.command(
        name="schedule",
        brief="schedule [course] [date]",
        usage=[
            ["course", "required", "Format as on school website"],
            ["date", "required", "DD.MM.YY(default: tomorrow)"]
        ],
        description="Sends schedule"
    )
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def schedule(self, ctx, course: str, date: str = None):
        """Sends schedule for class

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param course: str - Course name in format as on the school website
        :param date: str - Date in DD.MM.YY format (tomorrow as default)
        """
        # try:
        #     date = datetime.strptime(date, '%d.%m.%y')
        # except ValueError:
        #     return commands.BadArgument("**Date** should have **dd.mm.yy** format")
        date = datetime.strptime(date, '%d.%m.%y') if date else datetime.today()
        if date.weekday() < 5:
            date = datetime.strftime(date, '%d.%m.%y')
        else:  # Monday if tomorrow is weekend
            date = datetime.strftime(date + timedelta(days=7 - date.weekday()), '%d.%m.%y')
        timetables = await self.get_schedule(date=date, course=course)
        if not isinstance(timetables, dict):
            raise timetables

        date = days[datetime.strftime(datetime.strptime(date, '%d.%m.%y'), '%a')] + ' ' + date
        embed = discord.Embed(title=f"{course} {date}", description='', color=self.bot.ColorDefault)
        for key, value in timetables.items():
            for index, lesson in enumerate(value):
                embed.description += f"\n`{index+1}` {lesson}" if lesson else ''

        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(School(bot))

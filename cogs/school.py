# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json
import requests
import bs4
from bs4 import BeautifulSoup

lessons = {
        '📙physics': 'Физика', '📙maths': 'Математика', '📙ict': 'Информатика',
        '📗russian': 'Русский', '📗english': 'Английский',
        '📕literature': 'Литература', '📕history': 'История',
        '📘biology': 'Биология', '📘chemistry': 'Химия',
        '📒astronomy': 'Астрономия', '📒geography': 'География',
    }
days = {
    'Mon': 'понедельник', 'Tue': 'вторник', 'Wed': 'среда', 'Thu': 'четверг', 'Fri': 'пятница',
    'Sat': 'суббота', 'Sun': 'воскресенье'
}
courses = ('5а', '5б', '6а', '6б', '7а', '7б', '8а', '8б', '9а', '9б', '10м', '10х', '10э', '11м', '11х', '11э')


class School(commands.Cog):
    """
    A module for interacting with homework, schedule, etc.
    Inherits from command.Cog
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def get_homework(self, date):
        """Returns homework for a given date or ValueError if format is wrong
        Format of homework: [{
            lesson: str lesson name,
            content: str homework text, (can be empty)
            attachments: list homework files(photos), (can be empty)
            source: str link to the original message
        },]

        :param date: str - Date in DD.MM.YY format
        :return: dict(homework) or commands.BadArgument(Format error), str(date)
        """
        try:  # Argument error handler
            datetime.strptime(date, '%d.%m.%y')
        except ValueError:
            return commands.BadArgument("**Date** should have **dd.mm.yy** format"), date

        homework = []
        for channel in self.bot.get_channel(self.bot.HomeworkID).text_channels:  # Channels of SCHOOL category
            async for message in channel.history(limit=10):
                if date in message.content:
                    hw = {'lesson': str(message.channel), 'content': '', 'attachments': [], 'source': message.jump_url}
                    if message.content[message.content.find('\n')] != '1':
                        hw['content'] = message.content[message.content.find('\n'):]
                    if message.attachments:
                        hw['attachments'] = [attachment.url for attachment in message.attachments]
                    homework.append(hw)

        return homework

    async def get_schedule(self, date: str = None, course: str = None):
        """Returns the timetable from the school website

        :param date: str - The date for which you need to get the schedule (format: DD.MM.YY)
        :param course: str - School course to be returned
        :return: tables and date
        """
        response = requests.get(self.bot.ScheduleURL)
        soup = BeautifulSoup(response.text, 'lxml')

        tables = soup.find_all('tbody')
        headers = [h2 for h2 in soup.find_all('h2') if "Расписание" in h2.get_text()]
        content = {}  # {day: [table, table]}
        for index, header in enumerate(headers):
            day = header.get_text().split()[-2]
            content[day] = [tables[index*2], tables[index*2 + 1]]

        try:  # Argument error handler
            date = datetime.strptime(date, '%d.%m.%y') if date else datetime.today() + timedelta(days=1)
        except ValueError:
            return commands.BadArgument("**Date** should have **dd.mm.yy** format")
        if date.weekday() > 4:
            return commands.BadArgument("No lessons on weekends")
        if str(date.day) not in content.keys():
            return commands.BadArgument("Schedule not posted for the selected date")
        if course and course not in courses:
             return commands.BadArgument("Incorrect course")

        tables = []
        for table in content[str(date.day)]:
            new_table = []
            for row in table:  # Create table with replaced colspans
                if isinstance(row, bs4.element.Tag):  # There are NavigableStrings in rows
                    new_row = []
                    for index, col in enumerate(row):
                        if isinstance(col, bs4.element.Tag):  # There are NavigableStrings in cols
                            new_row.append(col.get_text().replace('\n', '').replace('\xa0', ''))
                            if 'colspan' in col.attrs:  # Replace all cols with colspan
                                for _ in range(int(col.attrs['colspan']) - 1):
                                    new_row.append(col.get_text().replace('\n', '').replace('\xa0', ''))
                    new_table.append(new_row)
            new_table = [[new_table[j][i] for j in range(len(new_table))] for i in range(len(new_table[0]))]  # rot90
            tables.append(new_table)

        schedule = {}
        for table in tables:  # Reformat to {course: [lessons]}
            for row in table[1:]:
                schedule[row[0]] = [lesson.capitalize() for lesson in row[2:]]

        return {course: schedule[course]} if course else schedule

    @commands.Cog.listener()
    async def on_ready(self):
        self.homework_and_schedule.start()

    @tasks.loop(hours=1)
    async def homework_and_schedule(self):
        """Automatically sends schedule for 11m class and homework as paginated embed to #schedule channel"""
        if self.homework_and_schedule.current_loop == 0:  # Avoid the first loop
            return

        tomorrow = datetime.today() + timedelta(days=1)
        if tomorrow.weekday() < 5:
            tomorrow = datetime.strftime(tomorrow, '%d.%m.%y')
        else:  # Monday if tomorrow is weekend
            tomorrow = datetime.strftime(tomorrow + timedelta(days=7 - tomorrow.weekday()), '%d.%m.%y')

        async for message in self.bot.get_channel(self.bot.ScheduleID).history(limit=None):  # Avoid existing messages
            if tomorrow in message.embeds[0].title:
                return

        homework = await self.get_homework(date=tomorrow)
        timetables = await self.get_schedule(date=tomorrow, course='11м')
        if not isinstance(timetables, dict):
            return

        date = days[datetime.strftime(datetime.strptime(tomorrow, '%d.%m.%y'), '%a')] + ' ' + tomorrow
        to_dump = {'homework': [], 'schedule': {'description': ''}}

        description = ''
        for key, value in timetables.items():
            for index, lesson in enumerate(value):
                description += f"\n`{index + 1}` {lesson}" if lesson else ''
        to_dump['schedule']['description'] = description
        embed = discord.Embed(title=f"Расписание {date}", description=description, color=self.bot.ColorDefault)

        if homework:
            for lesson in homework:
                if lessons[lesson['lesson']][:3] in description:
                    value = lesson['content'] + f" ([Источник]({lesson['source']}))"
                    if lesson['attachments']:
                        value += "\nПрикреплённые файлы: "
                        for index, link in enumerate(lesson['attachments']):
                            value += f"[№{index + 1}]({link})"
                            value += ', ' if index + 1 < len(lesson['attachments']) else ''
                    to_dump['homework'].append({'name': lessons[lesson['lesson']], 'value': value})
        else:
            to_dump['homework'].append({'name': "Ничего не задано", 'value': r"¯\_(ツ)_/¯"})

        file_name = '.'.join(date.split()[1].split('.')[::-1]) + ' ' + date.split()[0]
        with open(f"schedules/{file_name}.json", 'w', encoding='UTF-8') as file:
            json.dump(to_dump, file, ensure_ascii=False, indent=2)

        message = await self.bot.get_channel(self.bot.ScheduleID).send(embed=embed)
        for button in ('🔼', '➡️'):
            await message.add_reaction(emoji=button)

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
            file_name = '.'.join(title[2].split('.')[::-1]) + ' ' + title[1]
            date = ' '.join(title[1:])
            if current not in ("Расписание ", "ДЗ "):
                return
        except IndexError:
            return
        except AttributeError:
            return

        if (member == self.bot.user) or (not message.embeds):
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
    async def schedule(self, ctx, course: str, date: str = None):
        """Sends schedule for 11m class and homework as paginated embed to #schedule channel

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param course: str - Course name in format as on the school website
        :param date: str - Date in DD.MM.YY format (tomorrow as default)
        """
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

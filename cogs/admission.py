# -*- coding: utf-8 -*-

import discord
from discord.ext import commands, tasks
import os
import requests
import bs4
from bs4 import BeautifulSoup
from re import fullmatch
import gspread
from gspread.utils import rowcol_to_a1


class Admission(commands.Cog, name="admission"):
    """Updating the lists of applicants"""
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
        self.spreadsheet = service_account.open("Поступление СПб")

    @staticmethod
    async def get_spbu_lists(specialties):
        """Returns lists of applicants grouped by specialties

        :param specialties: list of strings - list of specialty codes
        :return: dict - {specialty: [[row], [row]]}
        """
        # Format error handler
        for specialty in specialties:
            if not fullmatch(r'\d\d[.]\d\d[.]\d\d', specialty):
                return RuntimeError(f"The **{specialty}** specialty has the wrong format")

        # Get soup
        response = requests.get(os.environ['SPBU_MAIN_LISTS_URL'])
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')

        # Get table of specialties
        table_of_specialties = []
        h3_list = soup.find_all('h3')
        for h3 in h3_list:
            specialty = h3.next_element
            profile = list(specialty.next_elements)[2]
            is_full_time = True if list(profile.next_elements)[2].get_text() == "Форма обучения: очная" else False
            link = list(profile.next_elements)[6]
            list_link = os.environ['SPBU_MAIN_URL'] + link.attrs['href'] if link.get_text() == "Госбюджетная" else None
            if is_full_time:
                code = specialty[:8]
                specialty = specialty + ' ' + profile
                table_of_specialties.append([code, specialty, list_link])

        # Get tables of applicants by specialty
        applicants_tables = {}
        types_of_conditions = {
            'Без ВИ': 'БВИ',
            'По результатам ВИ': 'ОК'
        }
        for row in table_of_specialties:
            code, specialty, applicants_table_link = row

            if applicants_table_link is None:
                continue
            if code not in specialties:
                continue

            response = requests.get(applicants_table_link)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'lxml')

            table_body = soup.tbody
            applicants = []
            for tr in table_body.find_all('tr'):
                tds = [td.get_text() for td in tr.find_all('td')]
                exams = [x.strip().replace(',', '.') if x.strip() else '0' for x in tds[4:6] + [tds[9]] + tds[6:9]]
                conditions = types_of_conditions[tds[2]]
                applicants.append(tds[:2] + [tds[3]] + [conditions] + exams + [tds[10]] + ['-'] + tds[11:13])

            applicants_tables[specialty] = applicants

        return applicants_tables

    @staticmethod
    async def get_spbetu_lists(specialties):
        """Returns lists of applicants grouped by specialties

        :param specialties: list of strings - list of specialty codes
        :return: dict - {specialty: [[row], [row]]}
        """
        # Format error handler
        for specialty in specialties:
            if not fullmatch(r'\d\d[.]\d\d[.]\d\d', specialty):
                return RuntimeError(f"The **{specialty}** specialty has the wrong format")

        # Get soup
        response = requests.get(os.environ['ETU_MAIN_LISTS_URL'])
        soup = BeautifulSoup(response.text, 'lxml')

        # Get table of specialties
        table_of_specialties = []
        table_body = soup.find(class_='table table-bordered').tbody
        for td in table_body:
            if not isinstance(td, bs4.element.Tag):
                continue

            row = td.find_all('td')

            code = row[0].get_text()
            specialty = row[1].get_text().replace('\t', '').replace('\r', '').replace('\n', '')
            try:
                applicants_table_link = os.environ['ETU_MAIN_URL'] + row[2].contents[0].attrs['href']
            except AttributeError:
                applicants_table_link = 'N/A'

            table_of_specialties.append([code, specialty, applicants_table_link])

        # Get tables of applicants by specialty
        applicants_tables = {}
        for row in table_of_specialties:
            code, specialty, applicants_table_link = row

            if code not in specialties:
                continue

            response = requests.get(applicants_table_link)
            soup = BeautifulSoup(response.text, 'lxml')

            table_body = soup.tbody
            applicants = []
            for tr in table_body.find_all('tr'):
                tds = [td.get_text().replace('\n', '') for td in tr.find_all('td')]
                applicants.append(tds[:6] + [tds[9]] + tds[6:9] + [tds[12]] + [tds[10]] + ['-', '-'])
            specialty = code + ' ' + specialty
            applicants_tables[specialty] = applicants

        return applicants_tables

    async def upload_data(self, university, applicants_tables):
        """Uploads the table to the main Google Spreadsheet

        :param university: str - Name of the university (future name of the sheet in the table)
        :param applicants_tables: dict - Tables of university applicants by specialties"""
        # Get worksheet object (create new or get old one)
        try:
            worksheet = self.spreadsheet.add_worksheet(title=university, rows='500', cols='500')
        except gspread.exceptions.APIError:
            worksheet = self.spreadsheet.worksheet(title=university)

        # Main
        row0, col0 = 1, 1
        for specialty, applicants in applicants_tables.items():
            # Get current table range
            start = rowcol_to_a1(row0, col0)
            end = rowcol_to_a1(row0 + 1 + len(applicants), col0 + 13)

            # Prepare data
            titles = [
                '№', 'СНИЛС / Код', 'П', 'Условия', 'Σ общая', 'Σ ЕГЭ', 'Σ ИД',
                'ЕГЭ 1', 'ЕГЭ 2', 'ЕГЭ 3', 'Согласие', 'ПП', 'ИД', 'Примечания'
            ]
            data = [[specialty] + [''] * 13, titles] + applicants

            # Update table
            worksheet.update(f"{start}:{end}", data)

            # Update whole table format
            worksheet.format(f"{start}:{end}", {
                'textFormat': {'fontSize': 11},
                'borders': {
                    'top': {'style': 'SOLID', 'width': 1},
                    'bottom': {'style': 'SOLID', 'width': 1},
                    'left': {'style': 'SOLID', 'width': 1},
                    'right': {'style': 'SOLID', 'width': 1}
                },
                'horizontalAlignment': 'CENTER',
            })

            # Update title format
            title_range = f"{start}:{rowcol_to_a1(row0, col0 + 13)}"
            worksheet.merge_cells(title_range, merge_type="MERGE_ALL")
            worksheet.format(title_range, {'textFormat': {'fontSize': 13, 'bold': True}})

            # Update header format
            header_range = f"{rowcol_to_a1(row0 + 1, col0)}:{rowcol_to_a1(row0 + 1, col0 + 13)}"
            worksheet.format(header_range, {'textFormat': {'fontSize': 12}})

            # Auto resize whole table
            worksheet.columns_auto_resize(col0, col0 + 13)

            # Next start position
            row0, col0 = 1, col0 + 15

    @tasks.loop(hours=1)
    async def applicants_table_updater(self, specialties):
        """Updates table of applicants hourly

        :param specialties: list of str - list of specialties
        """
        # Get tables
        data = {
            'СПбГЭТУ': await self.get_spbetu_lists(specialties),
            'СПбГУ': await self.get_spbu_lists(specialties)
        }

        # Main
        for university, applicants_tables in data.items():
            # Error handler
            if not isinstance(applicants_tables, dict):
                continue

            # Data upload
            if applicants_tables:
                await self.upload_data(university, applicants_tables)

    @commands.command(
        name="updater_start",
        brief="Start applicants table hourly updater",
        help=(
                "Starts an automatic parser for websites of universities with specified specialties. "
                "Update happens every hour "
        ),
        usage=[
            ["specialties", "required", "Specialty codes separated by spaces"],
        ]
    )
    async def updater_start(self, ctx, *args):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param args: list of str - Specialty codes
        """
        # Empty specialties error handler
        if not args:
            raise commands.MissingRequiredArgument(args)

        # Message send
        embed = discord.Embed(
            title="The table of applicants will be updated hourly",
            description="**Selected specialties:**\n" + '\n'.join(args),
            color=self.bot.ColorDefault
        )
        await ctx.send(embed=embed)

        # Task start
        self.applicants_table_updater.start(args)

    @commands.command(
        name="updater_stop",
        brief="Stop applicants table hourly updater",
        help=(
                "Stops an automatic parser for websites of universities with specified specialties. "
                "Completion occurs at the end of the current loop, if one is started"
        ),
        usage=[]
    )
    async def updater_stop(self, ctx):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        """
        # Message send
        embed = discord.Embed(
            title="Completion at the end of an iteration",
            description="**Total updates:** " + str(self.applicants_table_updater.current_loop),
            color=self.bot.ColorDefault
        )
        await ctx.send(embed=embed)

        # Gracefully stop the task
        self.applicants_table_updater.stop()

    @commands.command(
        name="updater_check",
        brief="Check if the loop is running",
        help=(
                "Checks the loop for running tasks and returns a response message "
        ),
        usage=[
            ["specialties", "required", "Specialty codes separated by spaces"],
        ]
    )
    async def updater_check(self, ctx):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        """
        embed = discord.Embed(
            description=f"Loop **is{' ' if self.applicants_table_updater.is_running() else ' not '}**running",
            color=self.bot.ColorDefault
        )
        # Data for developers
        embed.description += "\nCurrent task (for developers): \n||"
        embed.description += str(self.applicants_table_updater.get_task()) + "||"

        # Message send
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Admission(bot))

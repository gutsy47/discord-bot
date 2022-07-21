# -*- coding: utf-8 -*-

import asyncio
import discord
from discord.ext import commands, tasks
import os
import requests
import bs4
from bs4 import BeautifulSoup
from re import fullmatch
import gspread
from gspread.utils import rowcol_to_a1
import psycopg2
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from datetime import datetime


class Admission(commands.Cog, name="admission"):
    """Updating the lists of applicants"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Google Spread connection
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
    async def get_spbu_lists(specialties):
        """Returns lists of applicants grouped by specialties

        :param specialties: list of strings - list of specialty codes
        :return: dict - {specialty: [[row], [row]]}
        """
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

    @staticmethod
    async def get_itmo_lists(specialties):
        """Returns lists of applicants grouped by specialties

        :param specialties: list of strings - list of specialty codes
        :return: dict - {specialty: [[row], [row]]}
        """
        # Starting web driver
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")

        driver = webdriver.Chrome(service=Service("webdriver/chromedriver.exe"), options=options)
        driver.set_window_size(1920, 1080)

        # Get links for tables of applicants using selenium web driver
        driver.get("https://abit.itmo.ru/ratings/bachelor")
        driver.find_element(By.ID, 'tabs-tab-1').click()
        link_containers = driver.find_elements(By.XPATH, '//*[@id="tabs-tabpane-1"]/div[3]//div/a')
        links = [container.get_attribute('href') for container in link_containers]

        # Get tables of applicants data
        applicants_tables = {}
        for link in links:
            driver.get(link)
            # Get all rows
            try:
                table = WebDriverWait(driver, 10).until(
                    lambda x: x.find_elements(By.XPATH, '//*[@id="__next"]/div/main/div[2]/div/div/div/div[2]/div')
                )
            except TimeoutException:
                continue

            # Get specialty name with code
            specialty = driver.find_element(By.XPATH, '//*[@id="__next"]/div/main/div[2]/div/div/div/h2').text.lower()
            if specialty.split()[0] not in specialties:
                continue

            # Get each row data
            applicants = []
            for content in table:
                row = content.text.split('\n')
                similar = row[2:4] + row[-3:-5:-1] + row[4:7] + [row[-5]] + [row[-2]]
                similar = [text.split()[-1] for text in similar]
                exams_score = str(int(similar[2]) - int(similar[3]))
                row = [row[0].split()[0]] + [row[1]] + similar[0:3] + [exams_score] + similar[3:] + ['-', '-']
                applicants.append(row)
            applicants_tables[specialty] = applicants

        # Close web driver and return tables
        driver.quit()
        return applicants_tables

    async def upload_data(self, university, applicants_tables, update_time: datetime):
        """Uploads the table to the main Google Spreadsheet

        :param university: str - Name of the university (future name of the sheet in the table)
        :param applicants_tables: dict - Tables of university applicants by specialties
        :param update_time: datetime - Time of last update"""
        # Get worksheet object (create new or get old one)
        try:
            worksheet = self.spreadsheet.add_worksheet(title=university, rows='2000', cols='500')
        except gspread.exceptions.APIError:
            worksheet = self.spreadsheet.worksheet(title=university)

        # Main
        row0, col0 = 1, 1
        titles = [
            '№', 'СНИЛС / Код', 'Приоритет', 'Условия', 'Σ общая', 'Σ ЕГЭ', 'Σ ИД',
            'ЕГЭ 1', 'ЕГЭ 2', 'ЕГЭ 3', 'Согласие', 'ПП', 'ИД', 'Примечания'
        ]
        for specialty, applicants in applicants_tables.items():
            # Get current table range
            start = rowcol_to_a1(row0, col0)
            end = rowcol_to_a1(row0 + 1 + len(applicants), col0 + 13)

            # GSpread data updater, cycle breaks after 1st successful completion
            data = [[specialty] + [''] * 13, titles] + applicants
            while True:
                try:
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
                except gspread.exceptions.APIError:
                    await asyncio.sleep(delay=60)
                else:
                    break

            # Next start position
            row0, col0 = 1, col0 + 15
        worksheet.update('O1:O2', [['Обновлено'], [update_time.strftime('%H:%M %d.%m.%y')]])

    @tasks.loop(minutes=30)
    async def applicants_table_updater(self, specialties):
        """Updates table of applicants hourly

        :param specialties: list of str - list of specialties
        """
        # Get tables
        data = {}
        if 'СПбГЭТУ' in specialties.keys():
            data['СПбГЭТУ'] = await self.get_spbetu_lists(specialties['СПбГЭТУ'])
        if 'СПбГУ' in specialties.keys():
            data['СПбГУ'] = await self.get_spbu_lists(specialties['СПбГУ'])
        if 'ИТМО' in specialties.keys():
            data['ИТМО'] = await self.get_itmo_lists(specialties['ИТМО'])
        update_time = datetime.now()

        # Main
        for university, applicants_tables in data.items():
            # Error handler
            if not isinstance(applicants_tables, dict):
                continue

            # Data upload
            if applicants_tables:
                await self.upload_data(university, applicants_tables, update_time)

    @commands.Cog.listener()
    async def on_ready(self):
        # Check if task is already launched
        if self.applicants_table_updater.is_running():
            return

        # Get university-specialty pairs from database
        self.cursor.execute("SELECT * FROM specialty_upload;")
        specialties = {}
        for key, value in self.cursor.fetchall():
            if key in specialties.keys():
                specialties[key].append(value)
            else:
                specialties[key] = [value]

        # Updater start (Start if the database contains at least one specialty that needs to be updated else do nothing)
        if specialties:
            self.applicants_table_updater.start(specialties)

    @commands.command(
        name="updater_add",
        brief="Add new specialties to updater",
        help=(
                "Adds to the list of checked specialties at the university new ones that you specified"
        ),
        usage=[
            ["university", "required", "University name (Case sensitive)"],
            ["specialties", "required", "Specialty codes (space-separated)"]
        ]
    )
    async def updater_add(self, ctx, university, *args):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param university: str - University name or * (all universities)
        :param args: tuple of str - Specialty codes or * (all specialties)
        """
        # Empty specialties error handler
        if not args:
            raise commands.BadArgument(f"**specialties** is a required argument that is missing")

        # Specialties format error handler
        for specialty in args:
            if not fullmatch(r'\d\d[.]\d\d[.]\d\d', specialty):
                raise commands.BadArgument(f"The **{specialty}** specialty has the wrong format")

        # Database update
        for specialty in args:
            try:
                self.cursor.execute("INSERT INTO specialty_upload VALUES (%s, %s);", (university, specialty))
            except psycopg2.errors.UniqueViolation:
                continue
            except psycopg2.errors.ForeignKeyViolation:
                raise commands.BadArgument(f"**{university}** is a wrong university name")

        # Get university-specialty pairs from database
        self.cursor.execute("SELECT * FROM specialty_upload;")
        specialties = {}
        for key, value in self.cursor.fetchall():
            if key in specialties.keys():
                specialties[key].append(value)
            else:
                specialties[key] = [value]

        # Updater start or restart
        if self.applicants_table_updater.is_running():
            self.applicants_table_updater.restart(specialties)
        else:
            self.applicants_table_updater.start(specialties)

        # Message send
        embed = discord.Embed(title="Successfully added!", color=self.bot.ColorDefault)
        embed.description = f"These lists will be updated in the table of the **{university}**:\n"
        embed.description += '\n'.join(args)
        await ctx.send(embed=embed)

    @commands.command(
        name="updater_delete",
        brief="Delete specialties from updater",
        help=(
                "Removes the specified specialties from the list of updated"
        ),
        usage=[
            ["university", "required", "University name (Case sensitive) or '*' (All)"],
            ["specialties", "required", "Specialty codes (space-separated) or '*' (All)"]
        ]
    )
    async def updater_delete(self, ctx, university, *args):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param university: str - University name or * (all universities)
        :param args: tuple of str - Specialty codes or * (all specialties)
        """
        # Empty specialties error handler:
        if not args:
            raise commands.BadArgument(f"**specialties** is a required argument that is missing")

        # Specialties format error handler
        if '*' not in args:
            for specialty in args:
                if not fullmatch(r'\d\d[.]\d\d[.]\d\d', specialty):
                    raise commands.BadArgument(f"The **{specialty}** specialty has the wrong format")

        # Database update
        if '*' in args:
            if university == '*':
                self.cursor.execute("DELETE FROM specialty_upload;")
            else:
                self.cursor.execute("DELETE FROM specialty_upload WHERE university_name=%s;", (university, ))
        else:
            for specialty in args:
                if university == '*':
                    self.cursor.execute("DELETE FROM specialty_upload WHERE specialty_code=%s;", (specialty, ))
                else:
                    self.cursor.execute(
                        "DELETE FROM specialty_upload WHERE university_name=%s AND specialty_code=%s;",
                        (university, specialty)
                    )

        # Get university-specialty pairs from database
        self.cursor.execute("SELECT * FROM specialty_upload;")
        specialties = {}
        for key, value in self.cursor.fetchall():
            if key in specialties.keys():
                specialties[key].append(value)
            else:
                specialties[key] = [value]

        # Updater stop or restart
        if specialties:
            self.applicants_table_updater.restart(specialties)
        else:
            self.applicants_table_updater.stop()

        # Message send
        embed = discord.Embed(title="Successfully deleted!", color=self.bot.ColorDefault)
        university = 'all universities' if university == '*' else university
        embed.description = f"These lists have been deleted from **{university}**:\n"
        args = 'all specialties' if args == '*' else args
        embed.description += '\n'.join(args)
        await ctx.send(embed=embed)

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
        usage=[]
    )
    async def updater_check(self, ctx):
        """
        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        """
        embed = discord.Embed(
            title=f"Loop is{' ' if self.applicants_table_updater.is_running() else ' not '}running",
            description="**Total updates:** " + str(self.applicants_table_updater.current_loop),
            color=self.bot.ColorDefault
        )
        # Data for developers
        embed.description += "\nCurrent task (for developers): \n||"
        embed.description += str(self.applicants_table_updater.get_task()) + "||"

        # Message send
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Admission(bot))

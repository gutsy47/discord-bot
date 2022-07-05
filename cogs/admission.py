# -*- coding: utf-8 -*-

from discord.ext import commands
import os
import requests
import bs4
from bs4 import BeautifulSoup
from re import fullmatch


class Admission(commands.Cog, name="admission"):
    """Updating the lists of applicants"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
            speciality = row[1].get_text().replace('\t', '').replace('\r', '').replace('\n', '')
            try:
                applicants_table_link = os.environ['ETU_MAIN_URL'] + row[2].contents[0].attrs['href']
            except AttributeError:
                applicants_table_link = 'N/A'

            table_of_specialties.append([code, speciality, applicants_table_link])

        # Get tables of applicants by specialty
        applicants_tables = {}
        for row in table_of_specialties:
            code, speciality, applicants_table_link = row

            if code not in specialties:
                continue

            response = requests.get(applicants_table_link)
            soup = BeautifulSoup(response.text, 'lxml')

            table_body = soup.tbody
            applicants = []
            for tr in table_body.find_all('tr'):
                applicant = []
                for td in tr.find_all('td'):
                    applicant.append(td.get_text().replace('\n', ''))
                applicants.append(applicant)
            applicants_tables[f'{speciality} ({code})'] = sorted(applicants, key=lambda x: int(x[4]), reverse=True)

        return applicants_tables


def setup(bot):
    bot.add_cog(Admission(bot))

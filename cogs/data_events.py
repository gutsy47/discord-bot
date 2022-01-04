# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import psycopg2
from urllib.parse import urlparse
import os


class DataEvents(commands.Cog):
    """Responsible for the automatic collection of data"""
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

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Creates a server object and collects all information associated with it"""
        # Guild data
        self.cursor.execute("INSERT INTO ds_guild VALUES (%s, %s);", (guild.id, guild.name))

        # Guild channels
        for channel in guild.channels:
            if channel not in guild.categories:
                category_id = channel.category.id if channel.category else None
                is_system = channel.id == guild.system_channel.id if guild.system_channel else False
                self.cursor.execute(
                    "INSERT INTO ds_channel VALUES (%s, %s, %s, %s, %s, NULL, %s);",
                    (channel.id, guild.id, category_id, channel.name, str(channel.type), is_system)
                )

        # Guild members and bot users
        for member in guild.members:
            user = self.bot.get_user(member.id)
            self.cursor.execute(
                "INSERT INTO ds_user VALUES (%s, %s, %s) ON CONFLICT DO NOTHING;",
                (user.id, user.name, user.discriminator)
            )
            is_owner = member.id == member.guild.owner_id
            self.cursor.execute(
                "INSERT INTO ds_member VALUES (%s, %s, %s);",
                (member.id, member.guild.id, is_owner)
            )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Called when a guild changes: name, AFK channel, AFK timeout, etc"""
        if before.name != after.name:
            self.cursor.execute("UPDATE ds_guild SET guild_name=%s WHERE guild_id=%s;", (after.name, after.id))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when a guild is removed from the client"""
        # Current guild members
        self.cursor.execute("SELECT user_id FROM ds_member WHERE guild_id=%s;", (guild.id, ))
        guild_members = tuple(user_id[0] for user_id in self.cursor.fetchall())

        # Guild remove
        self.cursor.execute("DELETE FROM ds_guild WHERE guild_id=%s;", (guild.id, ))  # Guild remove

        # Same users in another guilds
        self.cursor.execute("SELECT user_id FROM ds_member WHERE user_id IN %s;", (guild_members, ))
        another_guild_members = tuple(user_id[0] for user_id in self.cursor.fetchall())

        # Users without member objects remove
        deleted_users = tuple(member for member in guild_members if member not in another_guild_members)
        self.cursor.execute("DELETE FROM ds_user WHERE user_id IN %s;", (deleted_users, ))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Called when a guild channel is created"""
        if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
            category_id = channel.category.id if channel.category else None
            self.cursor.execute(
                "INSERT INTO ds_channel VALUES (%s, %s, %s, %s, %s);",
                (channel.id, channel.guild.id, category_id, channel.name, str(channel.type))
            )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        """Called whenever a guild channel changes: name, topic, perms, etc"""
        if isinstance(before, discord.TextChannel) or isinstance(before, discord.VoiceChannel):
            category_id = after.category.id if after.category else None
            self.cursor.execute(
                "UPDATE ds_channel SET channel_name=%s, category_id=%s WHERE channel_id=%s;",
                (after.name, category_id, after.id)
            )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.GroupChannel):
        """Called when a guild channel is deleted"""
        if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
            self.cursor.execute("DELETE FROM ds_channel WHERE channel_id=%s;", (channel.id, ))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Called when a member joins a Guild"""
        # Add user to database if doesn't exist
        self.cursor.execute("SELECT 1 FROM ds_user WHERE user_id=%s;", (member.id, ))
        user_exists = self.cursor.fetchone()
        if not user_exists:  # Add user to database if doesn't exist
            user: discord.User = self.bot.get_user(member.id)
            self.cursor.execute(
                "INSERT INTO ds_user VALUES (%s, %s, %s);",
                (user.id, user.name, user.discriminator)
            )

        self.cursor.execute(
            "INSERT INTO ds_member VALUES (%s, %s, %s);",
            (member.id, member.guild.id, member.id == member.guild.owner_id)
        )

        # Send greeting message
        self.cursor.execute("SELECT is_greetings FROM ds_guild WHERE guild_id=%s;", (member.guild.id, ))
        is_greetings = self.cursor.fetchone()[0]
        if is_greetings and member.guild.system_channel:
            await member.guild.system_channel.send(f"{member.mention} has **joined** a server")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called when a member updates: status, activity, nickname, roles, pending"""
        pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves a Guild"""
        # Delete member
        self.cursor.execute("DELETE FROM ds_member WHERE user_id=%s AND guild_id=%s;", (member.id, member.guild.id))

        # Delete user if member was last user object
        self.cursor.execute("SELECT 1 FROM ds_member WHERE user_id=%s;", (member.id, ))
        user_exists = self.cursor.fetchone()
        if not user_exists:
            self.cursor.execute("DELETE FROM ds_user WHERE user_id=%s;", (member.id, ))

        # Send greeting message
        self.cursor.execute("SELECT is_greetings FROM ds_guild WHERE guild_id=%s;", (member.guild.id,))
        is_greetings = self.cursor.fetchone()[0]
        if is_greetings and member.guild.system_channel and not member == self.bot.user:
            await member.guild.system_channel.send(f"{member.mention} has **left** a server")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Called when user updates his: avatar, username, discriminator"""
        self.cursor.execute(
            "UPDATE ds_user SET user_name=%s, user_discriminator=%s WHERE user_id=%s;",
            (after.name, after.discriminator, after.id)
        )


def setup(bot):
    bot.add_cog(DataEvents(bot))

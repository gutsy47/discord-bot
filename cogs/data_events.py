# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import psycopg2
import os


class DataEvents(commands.Cog):
    """Responsible for the automatic collection of data"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Postgres connection
        with psycopg2.connect(
                dbname=os.environ['DATABASE_NAME'],
                user=os.environ['DATABASE_USER'],
                password=os.environ['DATABASE_PASSWORD']
        ) as self.connection:
            self.connection.autocommit = True
            self.cursor = self.connection.cursor()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Creates a server object and collects all information associated with it"""
        # Guild data
        self.cursor.execute(
            "INSERT INTO guild VALUES (%s, %s, NULL, False, %s);",
            (guild.id, guild.name, guild.created_at)
        )

        # Guild categories
        for category in guild.categories:
            self.cursor.execute("INSERT INTO category VALUES (%s, %s, %s);", (category.id, guild.id, category.name))

        # Guild channels
        for channel in guild.channels:
            if channel not in guild.categories:
                category_id = channel.category.id if channel.category else None
                is_system = channel.id == guild.system_channel.id if guild.system_channel else False
                self.cursor.execute(
                    "INSERT INTO channel VALUES (%s, %s, %s, %s, %s, False, False, NULL, %s);",
                    (channel.id, guild.id, category_id, channel.name, str(channel.type), is_system)
                )

        # Guild members and bot users
        for member in guild.members:
            user = self.bot.get_user(member.id)
            self.cursor.execute(
                "INSERT INTO \"user\" VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;",
                (user.id, user.name, user.discriminator, user.bot, user.created_at)
            )
            is_owner = member.id == member.guild.owner_id
            self.cursor.execute(
                "INSERT INTO member VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING;",
                (member.id, member.guild.id, member.display_name, is_owner, member.joined_at)
            )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        """Called when a guild changes: name, AFK channel, AFK timeout, etc"""
        if before.name != after.name:
            self.cursor.execute("UPDATE guild SET guild_name=%s WHERE guild_id=%s;", (after.name, after.id))

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Called when a guild is removed from the client"""
        self.cursor.execute("DELETE FROM guild WHERE guild_id=%s;", (guild.id,))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        """Called when a guild channel is created"""
        if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
            category_id = channel.category.id if channel.category else None
            self.cursor.execute(
                "INSERT INTO channel VALUES (%s, %s, %s, %s, %s, False, False, NULL, False);",
                (channel.id, channel.guild.id, category_id, channel.name, str(channel.type))
            )
        elif isinstance(channel, discord.CategoryChannel):
            self.cursor.execute(
                "INSERT INTO category VALUES (%s, %s, %s);",
                (channel.id, channel.guild.id, channel.name)
            )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        """Called whenever a guild channel changes: name, topic, perms, etc"""
        if isinstance(before, discord.TextChannel) or isinstance(before, discord.VoiceChannel):
            category_id = after.category.id if after.category else None
            self.cursor.execute(
                "UPDATE channel SET channel_name=%s, category_id=%s WHERE channel_id=%s;",
                (after.name, category_id, after.id)
            )
        elif isinstance(before, discord.CategoryChannel):
            self.cursor.execute("UPDATE category SET category_name=%s WHERE category.id=%s;", (after.name, after.id))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.GroupChannel):
        """Called when a guild channel is deleted"""
        if isinstance(channel, discord.TextChannel) or isinstance(channel, discord.VoiceChannel):
            self.cursor.execute("DELETE FROM channel WHERE channel_id=%s;", (channel.id, ))
        elif isinstance(channel, discord.CategoryChannel):
            self.cursor.execute("DELETE FROM category WHERE category_id=%s;", (channel.id, ))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Called when a member joins a Guild"""
        # Add user to database if doesn't exist
        self.cursor.execute("SELECT 1 FROM \"user\" WHERE user_id=%s;", (member.id, ))
        user_exists = self.cursor.fetchone()
        if not user_exists:  # Add user to database if doesn't exist
            user: discord.User = self.bot.get_user(member.id)
            self.cursor.execute(
                "INSERT INTO \"user\" VALUES (%s, %s, %s, %s, %s);",
                (user.id, user.name, user.discriminator, user.bot, user.created_at)
            )

        self.cursor.execute(
            "INSERT INTO member VALUES (%s, %s, %s, %s, %s);",
            (member.id, member.guild.id, member.display_name, member.id == member.guild.owner_id, member.joined_at)
        )

        # Send greeting message
        self.cursor.execute("SELECT is_greetings FROM guild WHERE guild_id=%s;", (member.guild.id, ))
        is_greetings = self.cursor.fetchone()[0]
        if is_greetings and member.guild.system_channel:
            await member.guild.system_channel.send(f"{member.mention} has **joined** a server")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Called when a member updates: status, activity, nickname, roles, pending"""
        self.cursor.execute("UPDATE member SET display_name=%s WHERE user_id=%s;", (after.display_name, after.id, ))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Called when a member leaves a Guild"""
        # Delete member
        self.cursor.execute("DELETE FROM member WHERE user_id=%s AND guild_id=%s;", (member.id, member.guild.id))

        # Delete user if member was last user object
        self.cursor.execute("SELECT 1 FROM member WHERE user_id=%s;", (member.id, ))
        user_exists = self.cursor.fetchone()
        if not user_exists:
            self.cursor.execute("DELETE FROM \"user\" WHERE user_id=%s;", (member.id, ))

        # Send greeting message
        self.cursor.execute("SELECT is_greetings FROM guild WHERE guild_id=%s;", (member.guild.id,))
        is_greetings = self.cursor.fetchone()[0]
        if is_greetings and member.guild.system_channel and not member == self.bot.user:
            await member.guild.system_channel.send(f"{member.mention} has **left** a server")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        """Called when user updates his: avatar, username, discriminator"""
        self.cursor.execute(
            "UPDATE \"user\" SET user_name=%s, user_discriminator=%s WHERE user_id=%s;",
            (after.name, after.discriminator, after.id)
        )

    @commands.command(
        name="toggle_greetings",
        brief="toggle_greetings",
        description="Turns on/off notification system for member join/remove in the system channel",
    )
    @commands.has_permissions(administrator=True)
    async def toggle_greetings(self, ctx):
        """Turns greetings on guild on/off"""
        # Update database
        self.cursor.execute("SELECT is_greetings FROM guild WHERE guild_id=%s;", (ctx.guild.id,))
        is_greetings = not self.cursor.fetchone()[0]
        self.cursor.execute("UPDATE guild SET is_greetings=%s WHERE guild_id=%s;", (is_greetings, ctx.guild.id))

        # Send message
        answer = '' if is_greetings else '**not**'
        embed = discord.Embed(description=f"Now I'll {answer} take care of greetings", color=self.bot.ColorDefault)
        if not ctx.guild.system_channel:
            embed.set_footer(text="Set the system channel in the server settings so that I can do it")
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(DataEvents(bot))

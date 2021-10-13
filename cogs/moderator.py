# -*- coding: utf-8 -*-
"""
TODO: Temp commands
TODO: Server stats
TODO: Server/User info by command
"""
import discord
from discord.ext import commands
from discord.utils import get


class Moderator(commands.Cog):
    """
    Provides server administration methods
    Inherits from command.Cog
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, member: discord.Member):
        """Cancel penalties(ban, kick, mute) by reaction and informs user if necessary

        :param reaction: discord.Reaction - Represents a reaction to a message
        :param member: discord.Member - User which added reaction (error if not in guild)
        """
        message: discord.Message = reaction.message
        channel: discord.TextChannel = message.channel
        try:
            penalty = message.embeds[0].author.name.split()[-1]
            if penalty not in ("banned", "kicked", "muted"):
                return
        except IndexError:
            return
        except AttributeError:
            return

        if (member == self.bot.user) or (not message.embeds):
            return
        if (not reaction.me or reaction.count > 1) and message.author.id == self.bot.user.id:
            await reaction.remove(member)

        name, discriminator = message.embeds[0].author.name.split()[-3].split('#')
        target = None
        for banned in await channel.guild.bans():
            if name == banned.user.name and discriminator == banned.user.discriminator:
                target = banned.user

        has_permissions = {
            "banned": member.guild_permissions.ban_members,
            "kicked": member.guild_permissions.kick_members,
            "muted": member.guild_permissions.mute_members
        }
        cancels = {"banned": "unbanned", "kicked": "invited again", "muted": "unmuted"}
        if has_permissions[penalty]:
            await message.remove_reaction(emoji="↩", member=self.bot.user)

            if penalty == "banned":
                await message.guild.unban(target)
            if penalty == "muted":
                muted_role = get(message.guild.roles, name='muted')
                target = get(message.guild.members, name=name, discriminator=discriminator)
                await target.remove_roles(muted_role)
            if penalty != "muted":
                if target in self.bot.get_all_members():
                    link = await channel.create_invite(max_uses=1)
                    embed = discord.Embed(color=self.bot.ColorDefault)
                    embed.title = f"You have been {cancels[penalty]} from {channel.guild}"
                    embed.description = f"Hey look! I have a onetime invite for you ([Click here!]({link}))"
                    embed.set_footer(text=str(member), icon_url=member.avatar_url)
                    await target.send(embed=embed)

            embed = discord.Embed(color=self.bot.ColorDefault)
            embed.set_author(name=f"{target} was {cancels[penalty]}", icon_url=f"{target.avatar_url}")
            await channel.send(embed=embed)
            await message.add_reaction("✅")

    @commands.command(
        name="ban",
        brief="ban [user] (reason)",
        usage=[
            ["user", "required", "Member mention or ID"],
            ["reason", "optional", "Reason, may include spaces"]
        ],
        description="Ban a member from the server"
    )
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Ban a member from the server, informs banned user

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            raise commands.MissingRole(f"{ctx.author.top_role} or higher")
        if member.bot:
            embed = discord.Embed(title="Something went wrong", color=self.bot.ColorError)
            embed.description = "🚫 I can`t ban a bot"
            return await ctx.send(embed=embed)

        embed = discord.Embed(description=f"**Reason:** {reason}", color=self.bot.ColorDefault)
        embed.set_author(name=f"{member} was banned", icon_url=member.avatar_url)
        embed.set_footer(text="Use ↩️ button to unban this user")
        message = await ctx.send(embed=embed)
        await message.add_reaction("↩")

        embed = discord.Embed(title=f"You have been banned from {ctx.guild}", color=self.bot.ColorDefault)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Unban server", value=self.bot.BannedGuildInvite, inline=False)
        embed.set_footer(text=ctx.author, icon_url=ctx.author.avatar_url)
        await member.send(embed=embed)

        await ctx.guild.ban(member, reason=reason)

    @commands.command(
        name="unban",
        brief="unban [user]",
        usage=[
            ["user", "required", "Banned user mention or ID"],
        ],
        description="Unban a member from the server"
    )
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: discord.User):
        """Unban a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param user: discord.User - Banned user which was banned (error if not banned)
        """
        await ctx.guild.unban(user)
        link = await ctx.channel.create_invite(max_uses=1)
        embed = discord.Embed(color=self.bot.ColorDefault)
        embed.title = f"You have been unbanned from {ctx.guild}"
        embed.description = f"Hey look! I have a onetime invite for you ([Click here!]({link}))"
        embed.set_footer(text=ctx.author, icon_url=ctx.author.avatar_url)
        try:
            await user.send(embed=embed)
        except discord.Forbidden:
            pass
        embed = discord.Embed(color=self.bot.ColorDefault)
        embed.set_author(name=f"{user} was unbanned", icon_url=f"{user.avatar_url}")
        await ctx.send(embed=embed)

    @commands.command(
        name="kick",
        brief="kick [user] (reason)",
        usage=[
            ["user", "required", "Member mention or ID"],
            ["reason", "optional", "Reason, may include spaces"]
        ],
        description="Kick a member from the server"
    )
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Kick a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            raise commands.MissingRole(f"{ctx.author.top_role} or higher")
        if member.bot:
            embed = discord.Embed(title="Something went wrong", color=self.bot.ColorError)
            embed.description = "🚫 I can`t kick a bot"
            return await ctx.send(embed=embed)

        embed = discord.Embed(description=f"**Reason:** {reason}", color=self.bot.ColorDefault)
        embed.set_author(name=f"{member} was kicked", icon_url=member.avatar_url)
        await ctx.send(embed=embed)

        embed = discord.Embed(title=f"You have been kicked from {ctx.guild}", color=self.bot.ColorDefault)
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=ctx.author, icon_url=ctx.author.avatar_url)
        await member.send(embed=embed)

        await ctx.guild.kick(member)

    @commands.command(
        name="mute",
        brief="mute [user] (reason)",
        usage=[
            ["user", "required", "Member mention or ID"],
            ["reason", "optional", "Reason, may include spaces"]
        ],
        description="Mute a member in the server"
    )
    @commands.has_permissions(kick_members=True)
    async def mute(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Mute a member in the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            raise commands.MissingRole(f"{ctx.author.top_role} or higher")
        if member.bot:
            embed = discord.Embed(title="Something went wrong", color=self.bot.ColorError)
            embed.description = "🚫 I can`t mute a bot"
            return await ctx.send(embed=embed)

        muted_role = get(ctx.guild.roles, name='muted')
        if not muted_role:
            await ctx.send("I couldn't found the **muted** role, You have to add and set up it")
            return
        embed = discord.Embed(description=f"**Reason:** {reason}", color=self.bot.ColorDefault)
        embed.set_author(name=f"{member} was muted", icon_url=f"{member.avatar_url}")
        embed.set_footer(text="Use ↩️ button to unmute this user")
        message = await ctx.send(embed=embed)
        await message.add_reaction("↩")
        await member.add_roles(muted_role)

    @commands.command(
        name="unmute",
        brief="unmute [user]",
        usage=[
            ["user", "required", "Muted user mention or ID"],
        ],
        description="Unmute a member from the server"
    )
    @commands.has_permissions(kick_members=True)
    async def unmute(self, ctx, member: discord.Member):
        """Unmute a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        """
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            raise commands.MissingRole(f"{ctx.author.top_role} or higher")
        if member.bot:
            embed = discord.Embed(title="Something went wrong", color=self.bot.ColorError)
            embed.description = "🚫 I can`t unmute a bot"
            return await ctx.send(embed=embed)

        muted_role = get(ctx.guild.roles, name='muted')
        embed = discord.Embed(color=self.bot.ColorDefault)
        embed.set_author(name=f"{member} was unmuted", icon_url=f"{member.avatar_url}")
        await ctx.send(embed=embed)
        await member.remove_roles(muted_role)

    @commands.command(
        name="clear",
        brief="clear (amount) (member)",
        usage=[
            ["amount", "optional", "Number of messages"],
            ["member", "optional", "Whose messages"]
        ],
        description="Delete a channel`s messages"
    )
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, limit: str = "all", member: discord.Member = None):
        """Delete a channel`s messages

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param limit: any - Amount of messages to delete (all or empty will change to len(history), error if 0)
        :param member: discord.Member - Guild member (error if not in it)
        """
        try:
            history = await ctx.channel.history(limit=None).flatten()
            limit = len(history) if limit == "all" else abs(int(limit))
            limit = limit if limit > 0 else int("ValueError")
            whose = f" of {member.mention}" if member else ''
            messages_to_delete = []
        except ValueError:
            raise commands.BadArgument("**limit** should be '**all**' or **positive integer**")

        await ctx.message.delete()

        if not member:  # Default clean
            messages_to_delete = history
            await ctx.channel.purge(limit=limit)

        if member:  # Member clean
            for message in history:
                if len(messages_to_delete) == limit:
                    break
                if message.author == member:
                    messages_to_delete.append(message)
            await ctx.channel.delete_messages(messages_to_delete)

        limit = min(limit, len(messages_to_delete))
        author = ctx.author.mention
        if limit > 0:
            embed = discord.Embed(description=f"{author} deleted {limit} messages{whose}", color=self.bot.ColorDefault)
        else:
            embed = discord.Embed(description=f"There are no messages{whose} here", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)

    @commands.command(
        name="ping",
        brief="ping",
        description="Returns delay time"
    )
    async def ping(self, ctx):
        """Bot health check. Returns delay time

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        """
        latency = round(self.bot.latency*1000)
        embed = discord.Embed(description=f":ping_pong: Pong! The ping is **{latency}**ms", color=self.bot.ColorDefault)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Moderator(bot))

# -*- coding: utf-8 -*-
"""
TODO: Temp commands
TODO: Server stats
"""
import discord
from discord.ext import commands
from discord.utils import get


class Moderator(commands.Cog):
    """Provides server administration methods"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, member: discord.Member):
        """Cancel penalties(ban, mute) by reaction and informs user if necessary

        :param reaction: discord.Reaction - Represents a reaction to a message
        :param member: discord.Member - User which added reaction (error if not in guild)
        """
        message: discord.Message = reaction.message
        channel: discord.TextChannel = message.channel

        if isinstance(channel, discord.DMChannel):
            return
        if message.author.id != self.bot.user.id or member == self.bot.user:
            return
        if reaction.count > 1:
            await reaction.remove(member)

        try:
            penalty = reaction.message.embeds[0].author.name.split()[-1]
            if penalty not in ("banned", "muted"):
                return
        except IndexError:
            return
        except AttributeError:
            return

        has_permissions = {
            "banned": member.guild_permissions.ban_members,
            "muted": member.guild_permissions.manage_roles
        }
        if has_permissions[penalty]:
            name, discriminator = message.embeds[0].author.name.split()[-3].split('#')
            embed = discord.Embed(color=self.bot.ColorDefault)
            if penalty == "banned":
                banned_users = [entry.user for entry in await channel.guild.bans()]
                target = get(banned_users, name=name, discriminator=discriminator)
                if target in self.bot.get_all_members():
                    invite_link = await channel.create_invite(max_uses=1)
                    embed_invite = discord.Embed(
                        title=f"You have been unbanned from {channel.guild}",
                        description=f"Hey look! I have a onetime invite for you ([Click here!]({invite_link}))",
                        color=self.bot.ColorDefault,
                    )
                    embed_invite.set_footer(text=str(member), icon_url=member.avatar_url)
                    await target.send(embed=embed_invite)
                else:
                    embed.set_footer(text="Failed to send an invite")
                embed.set_author(name=f"{target} was unbanned", icon_url=f"{target.avatar_url}")
                await message.guild.unban(target)
                await channel.send(embed=embed)
            elif penalty == "muted":
                target = get(channel.guild.members, name=name, discriminator=discriminator)
                muted_role = get(message.guild.roles, name='muted')
                await target.remove_roles(muted_role)
                embed.set_author(name=f"{target} was unmuted", icon_url=f"{target.avatar_url}")
                await channel.send(embed=embed)

            await message.remove_reaction(emoji="↩", member=self.bot.user)
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
    @commands.guild_only()
    async def ban(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Ban a member from the server, inform banned user

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if member.guild_permissions.administrator:
            raise commands.BadArgument("I can't kick/ban/mute administrator")
        if ctx.author != ctx.guild.owner and ctx.author.top_role <= member.top_role:
            raise commands.MissingRole

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
    @commands.guild_only()
    async def unban(self, ctx, user: discord.User):
        """Unban a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param user: discord.User - User which was banned (error if not banned)
        """
        await ctx.guild.unban(user)
        embed = discord.Embed(color=self.bot.ColorDefault)
        embed.set_author(name=f"{user} was unbanned", icon_url=f"{user.avatar_url}")
        try:
            invite_link = await ctx.channel.create_invite(max_uses=1)
            embed_invite = discord.Embed(
                title=f"You have been unbanned from {ctx.guild}",
                description=f"Hey look! I have a onetime invite for you ([Click here!]({invite_link}))",
                color=self.bot.ColorDefault,
            )
            embed_invite.set_footer(text=ctx.author, icon_url=ctx.author.avatar_url)
            await user.send(embed=embed_invite)
        except discord.Forbidden:
            embed.set_footer(text="Failed to send an invite")
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
    @commands.guild_only()
    async def kick(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Kick a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if member.guild_permissions.administrator:
            raise commands.BadArgument("I can't kick/ban/mute administrator")
        if ctx.author != ctx.guild.owner and ctx.author.top_role <= member.top_role:
            raise commands.MissingRole

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
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def mute(self, ctx, member: discord.Member, *, reason: str = "Not specified"):
        """Mute a member in the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        :param reason: str - Ban reason, may include spaces (default = "Not specified")
        """
        if member.guild_permissions.administrator:
            raise commands.BadArgument("I can't kick/ban/mute administrator")
        if ctx.author != ctx.guild.owner and ctx.author.top_role <= member.top_role:
            raise commands.MissingRole

        muted_role = get(ctx.guild.roles, name='muted')
        if not muted_role:
            return await ctx.send("I couldn't found the **muted** role, You have to add and set up it")
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
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unmute(self, ctx, member: discord.Member):
        """Unmute a member from the server

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param member: discord.Member - Guild member (error if not in it)
        """
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
    @commands.guild_only()
    async def clear(self, ctx, limit: str = "all", member: discord.Member = None):
        """Delete a channel`s messages

        :param ctx: discord.ext.commands.Context - Represents the context in which a command is being invoked under
        :param limit: any - Amount of messages to delete (all or empty will change to len(history), error if 0)
        :param member: discord.Member - Guild member (error if not in it)
        """
        await ctx.message.delete()

        history = await ctx.channel.history(limit=None).flatten()
        limit = len(history) if limit == "all" else abs(int(limit))
        if limit <= 0:
            raise commands.BadArgument("**limit** should be '**all**' or **positive integer**")

        messages_to_delete = []
        if not member:  # Default clean
            messages_to_delete = history
            await ctx.channel.purge(limit=limit)
        elif member:  # Member clean
            for message in history:
                if len(messages_to_delete) == limit:
                    break
                if message.author == member:
                    messages_to_delete.append(message)
            await ctx.channel.delete_messages(messages_to_delete)

        deleted = min(limit, len(messages_to_delete))
        author = ctx.author.mention
        whose = f" of {member.mention}" if member else ''
        embed = discord.Embed(description=f"{author} deleted {deleted} messages{whose}", color=self.bot.ColorDefault)
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

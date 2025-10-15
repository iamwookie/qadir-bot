import logging

import discord
from discord.ext import commands

from config import config
from core import Cog, Qadir
from utils import dt_to_psx
from utils.embeds import ErrorEmbed

logger = logging.getLogger("qadir")


class UtilityCog(Cog, name="Utility"):
    """A cog for utility commands."""

    @discord.slash_command(description="Ping the application")
    async def ping(self, ctx: discord.ApplicationContext) -> None:
        """
        Ping the application.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        await ctx.respond("🟢 Pong!", ephemeral=True)

    @discord.slash_command(description="Information about the application")
    async def info(self, ctx: discord.ApplicationContext) -> None:
        """
        Get information about the application.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        dev_id = 244662779745665026

        embed = discord.Embed(title="App Information", description=f"A magical application created by <@{dev_id}>", colour=0x00FF00)
        embed.add_field(name="Version", value=f"`{config['app']['version']}`")
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 100)} ms`")
        embed.add_field(name="Guilds", value=f"`{len(self.bot.guilds)}`", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(description="Get a list of available commands")
    async def help(self, ctx: discord.ApplicationContext) -> None:
        """
        Get a list of available commands.

        Args:
            ctx (discord.ApplicationContext): The application context
        """

        await ctx.defer(ephemeral=True)

        embed = discord.Embed(title="Help", description="Need some help? Gotchu", colour=0xFFFFFF)

        # Group commands by category for better organization
        utility_commands: list[tuple[str, str]] = []
        proposal_commands: list[tuple[str, str]] = []
        event_commands: list[tuple[str, str]] = []
        hangar_commands: list[tuple[str, str]] = []
        other_commands: list[tuple[str, str]] = []

        # Iterate through cogs mapping (qualified_name -> cog)
        for cog_name, cog in self.bot.cogs.items():
            cog_name_lower = cog_name.lower()

            # Get all commands from this cog
            for command in cog.get_commands():
                if isinstance(command, discord.SlashCommand):
                    # Handle individual SlashCommands
                    command_is_available = True

                    # Check guild restrictions
                    if hasattr(command, "guild_ids") and command.guild_ids:
                        command_is_available = ctx.guild and ctx.guild.id in command.guild_ids

                    if command_is_available:
                        command_name = f"/{command.qualified_name}"
                        command_desc = command.description or "No description provided"

                        # Categorize commands based on cog name
                        if cog_name_lower == "utility":
                            utility_commands.append((command_name, command_desc))
                        elif cog_name_lower == "proposals":
                            proposal_commands.append((command_name, command_desc))
                        elif cog_name_lower == "events":
                            event_commands.append((command_name, command_desc))
                        elif cog_name_lower == "hangar":
                            hangar_commands.append((command_name, command_desc))
                        else:
                            other_commands.append((command_name, command_desc))
                elif isinstance(command, discord.SlashCommandGroup):
                    # Handle SlashCommandGroup and its subcommands
                    group_available = True

                    # Check guild restrictions for the group
                    if hasattr(command, "guild_ids") and command.guild_ids:
                        group_available = ctx.guild and ctx.guild.id in command.guild_ids

                    if group_available:
                        # Add subcommands
                        for subcommand in command.subcommands:
                            if isinstance(subcommand, discord.SlashCommand):
                                subcommand_name = f"/{subcommand.qualified_name}"
                                subcommand_desc = subcommand.description or "No description provided"

                                # Categorize subcommands based on cog name
                                if cog_name_lower == "utility":
                                    utility_commands.append((subcommand_name, subcommand_desc))
                                elif cog_name_lower == "proposals":
                                    proposal_commands.append((subcommand_name, subcommand_desc))
                                elif cog_name_lower == "events":
                                    event_commands.append((subcommand_name, subcommand_desc))
                                elif cog_name_lower == "hangar":
                                    hangar_commands.append((subcommand_name, subcommand_desc))
                                else:
                                    other_commands.append((subcommand_name, subcommand_desc))

        if utility_commands:
            for name, desc in utility_commands:
                embed.add_field(name=f"`{name}`", value=f"᲼⤷ {desc}", inline=False)

        if proposal_commands:
            embed.add_field(name="📋 **Proposal Commands**", value="", inline=False)
            for name, desc in proposal_commands:
                embed.add_field(name=f"`{name}`", value=f"᲼⤷ {desc}", inline=False)

        if event_commands:
            embed.add_field(name="🏆 **Event Commands**", value="", inline=False)
            for name, desc in event_commands:
                embed.add_field(name=f"`{name}`", value=f"᲼⤷ {desc}", inline=False)

        if hangar_commands:
            embed.add_field(name="🚀 **Hangar Commands**", value="", inline=False)
            for name, desc in hangar_commands:
                embed.add_field(name=f"`{name}`", value=f"᲼⤷ {desc}", inline=False)

        if other_commands:
            embed.add_field(name="🔧 **Other Commands**", value="", inline=False)
            for name, desc in other_commands:
                embed.add_field(name=f"`{name}`", value=f"᲼⤷ {desc}", inline=False)

        # Add footer with guild info
        if ctx.guild:
            embed.set_footer(text=f"Commands available in {ctx.guild.name}")
        else:
            embed.set_footer(text="Commands available globally")

        await ctx.followup.send(embed=embed, ephemeral=True)

    @discord.slash_command(description="Find information about a user")
    @discord.option("user_id", str, description="A user to find by ID")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def find(self, ctx: discord.ApplicationContext, user_id: str | None = None) -> None:
        """
        Get information about a user.

        Args:
            ctx (discord.ApplicationContext): The application context
            user_id (str | None): The user ID to look up. If None, defaults to the command invoker.
        """

        await ctx.defer(ephemeral=True)

        user_id_str = user_id.strip() if user_id else str(ctx.author.id)
        not_found_embed = ErrorEmbed("Not Found", "The user was not found.")

        try:
            user = await self.bot.get_or_fetch_user(int(user_id_str))
        except discord.NotFound:
            await ctx.followup.send(embed=not_found_embed, ephemeral=True)
            return
        except ValueError:
            await ctx.followup.send(
                embed=ErrorEmbed("Invalid User ID", "Invalid user ID provided, e.g. 123456789012345678"), ephemeral=True
            )
            return

        if not user:
            await ctx.followup.send(embed=not_found_embed, ephemeral=True)
            return

        embed = discord.Embed(title="User Information", colour=0xFFFFFF)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Name", value=f"`{str(user)}`", inline=False)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{dt_to_psx(user.created_at)}:R>", inline=False)

        if isinstance(ctx.guild, discord.Guild):
            try:
                member = ctx.guild.get_member(user.id) or await ctx.guild.fetch_member(user.id)

                if member.joined_at:
                    embed.add_field(name="Server Joined", value=f"<t:{dt_to_psx(member.joined_at)}:R>", inline=False)

                if member.roles:
                    roles: list[str] = [role.mention for role in member.roles if role.id != ctx.guild.id]
                    embed.add_field(name="Server Roles", value=" ".join(roles) if roles else "None", inline=False)
            except Exception:
                # Intentionally ignored
                pass

        if user.accent_colour:
            embed.add_field(name="Accent Colour" if user.banner else "Banner Colour", value=f"`{user.accent_colour}`")

        if user.banner:
            embed.set_image(url=user.banner.url)

        if user.bot:
            embed.set_footer(text="⚠️ This user is a bot.")

        await ctx.followup.send(embed=embed, ephemeral=True)


def setup(bot: Qadir) -> None:
    """
    Load the UtilityCog into the bot.

    Args:
        bot (Qadir): The bot instance to load the cog into.
    """

    bot.add_cog(UtilityCog(bot))

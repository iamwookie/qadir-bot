from datetime import datetime, timezone

import discord


class SuccessEmbed(discord.Embed):
    """
    A custom embed class for displaying success messages.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(colour=discord.Colour.green(), **kwargs)


class ErrorEmbed(discord.Embed):
    """
    A custom embed class for displaying error messages.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(colour=discord.Colour.red(), **kwargs)


class HangarEmbed(discord.Embed):
    """
    A custom embed class for displaying hangar status information.
    """

    def __init__(self, state: dict, **kwargs) -> None:
        """
        Create the hangar status embed.

        Args:
            state (dict): The current hangar state information
        """

        super().__init__(title="Star Citizen Executive Hangar Status", color=state["color"], timestamp=datetime.now(timezone.utc), **kwargs)

        # Author field
        self.set_author(name="Provided by: exec.xyxyll.com", url="https://exec.xyxyll.com")

        # Status field
        self.add_field(name="🎯 Current Status", value=f"**{state['status']}**", inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        next_status_change: datetime = state["next_status_change"]
        next_status_change_timestamp = int(next_status_change.timestamp())
        self.add_field(name="⏰ Next Status Change", value=f"<t:{next_status_change_timestamp}:R>", inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        next_light_change: datetime = state["next_light_change"]
        next_light_change_timestamp = int(next_light_change.timestamp())
        self.add_field(name="⏰ Next Light Change", value=f"<t:{next_light_change_timestamp}:R>", inline=True)

        # LED lights status (visual indicator)
        lights_display = " ".join(state["lights"])
        self.add_field(name="💡 LED Status", value=lights_display, inline=False)

        # Add explanation based on new timing system
        if state["status"] == "Hangar Closed":
            self.add_field(
                name="ℹ️ Offline Phase",
                value="Executive hangars are currently offline. LED progression indicates time until reopening.",
                inline=False,
            )
        elif state["status"] == "Hangar Open":
            self.add_field(
                name="ℹ️ Online Phase",
                value="Executive hangars are operational! LED progression shows time remaining until closure.",
                inline=False,
            )

        self.set_footer(text="Updated for Star Citizen Patch 4.3.1-LIVE (Ver 10321721)")

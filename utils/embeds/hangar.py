from datetime import datetime

import discord

from ..common import dt_to_psx


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

        super().__init__(title="Executive Hangar Status", color=state["color"], timestamp=discord.utils.utcnow(), **kwargs)

        # Author field
        self.set_author(name="Provided by: exec.xyxyll.com", url="https://exec.xyxyll.com")

        # Status field
        self.add_field(name="🎯 Current Status", value=f"**{state['status']}**", inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        next_status_change: datetime = state["next_status_change"]
        self.add_field(name="⏰ Next Status Change", value=f"<t:{dt_to_psx(next_status_change)}:R>", inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        next_light_change: datetime = state["next_light_change"]
        self.add_field(name="⏰ Next Light Change", value=f"<t:{dt_to_psx(next_light_change)}:R>", inline=True)

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

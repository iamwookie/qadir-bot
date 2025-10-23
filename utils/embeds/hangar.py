import discord

from models.hangar import HangarState

from ..common import dt_to_psx
from ..enums import HangarStatus


class HangarEmbed(discord.Embed):
    """A custom embed class for displaying hangar status information."""

    def __init__(self, state: HangarState, **kwargs) -> None:
        """
        Create the hangar status embed.

        Args:
            state (HangarState): The current hangar state information
        """

        super().__init__(title="Executive Hangar Status", color=state.color, timestamp=discord.utils.utcnow(), **kwargs)

        # Author field
        self.set_author(name="Provided by: exec.xyxyll.com", url="https://exec.xyxyll.com")

        # Status field
        status = "🟢 **Online**" if state.status == HangarStatus.ONLINE else "🔴 **Offline**"
        self.add_field(name="Current Status", value=status, inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        self.add_field(name="Next Status Change", value=f"<t:{int(dt_to_psx(state.next_status_change))}:R>", inline=True)

        # Discord timestamp field - shows exact time in user's timezone
        self.add_field(name="Next Light Change", value=f"<t:{int(dt_to_psx(state.next_light_change))}:R>", inline=True)

        # LED lights status (visual indicator)
        self.add_field(name="LED Status", value=" ".join(state.lights), inline=False)

        # Add explanation based on new timing system
        if state.status == HangarStatus.OFFLINE:
            self.add_field(
                name="Offline Phase",
                value="Executive hangars are currently `OFFLINE`, the LED progression indicates time until reopening",
                inline=False,
            )
        elif state.status == HangarStatus.ONLINE:
            self.add_field(
                name="Online Phase",
                value="Executive hangars are currently `ONLINE`, the LED progression indicates time until closure",
                inline=False,
            )

        self.set_footer(text="Updated for Star Citizen Patch 4.3.2-LIVE (Server Version 10452200)")

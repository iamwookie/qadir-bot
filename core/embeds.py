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

        super().__init__(
            title="🚀 Star Citizen Executive Hangar Status", color=state["color"], timestamp=datetime.now(timezone.utc), **kwargs
        )

        # Status field
        self.add_field(name="🎯 Current Status", value=f"**{state['status']}**", inline=True)

        # Timer field
        self.add_field(name="⏰ Time Remaining", value=f"`{state['time_left']}`", inline=True)

        # Phase description
        self.add_field(name="📋 Phase Info", value=state["phase_description"], inline=True)

        # Light status (visual indicator)
        lights_display = " ".join(state["lights"])
        self.add_field(name="💡 Hangar Lights", value=lights_display, inline=False)

        # Add explanation
        if state["status"] == "Hangar Closed":
            self.add_field(name="ℹ️ Red Phase", value="Lights turn green every 24 minutes as hangar opening approaches.", inline=False)
        elif state["status"] == "Hangar Open":
            self.add_field(name="ℹ️ Green Phase", value="Lights turn black every 12 minutes as reset approaches.", inline=False)
        elif state["status"] == "Hangar Resetting":
            self.add_field(name="ℹ️ Black Phase", value="All systems resetting. Hangar will reopen soon.", inline=False)

        self.set_footer(text="Data from contestedzonetimers.com")

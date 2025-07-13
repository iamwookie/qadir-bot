import discord


class ErrorEmbed(discord.Embed):
    """
    A custom embed class for displaying error messages.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(colour=discord.Colour.red(), **kwargs)

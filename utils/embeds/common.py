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

    def __init__(self, title: str | None = "Uh Oh", description: str = "Something went wrong 😞", **kwargs) -> None:
        super().__init__(title=title, description=description, colour=discord.Colour.red(), **kwargs)

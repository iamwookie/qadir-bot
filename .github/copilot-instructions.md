# Qadir Bot - AI Agent Instructions

## Quick Start
**See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed system design, data flows, and component interactions.**

## Project Overview
Qadir is a modular Discord bot built with **Pycord** that provides utility, proposal voting, event/loot tracking, hangar management, and voice channel features. It uses **MongoDB + Beanie** for data persistence, **Upstash Redis** for caching, and modern Discord slash commands.

**Key Tech Stack:** Python 3.12.3 | Pycord (discord.py fork) | Beanie ODM | MongoDB | Upstash Redis | Poetry

## Development Workflow

### Setup
```powershell
poetry install --no-root
# Create config.dev.toml with your Discord/MongoDB/Redis credentials
```

### Run
```powershell
poetry run python main.py
```

### Configuration
1. Copy `config.toml` → `config.dev.toml` and update credentials
2. Environment variables (`.env`): `DISCORD_TOKEN`, `MONGODB_URI`, `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`, `APP_DEBUG=true`, `PYTHON_ENV=development`

### Logging
- Logger name: `"qadir"` (configured in `main.py`)
- Writes to console + `qadir.log`
- Debug level set by `APP_DEBUG` env var
- Use in cogs: `logger = logging.getLogger("qadir")`

## Common Tasks

### Add a new slash command
1. Create cog file in `cogs/` extending `core.Cog`
2. Define command with `@discord.slash_command()` or `@discord.SlashCommandGroup()`
3. Load in `main.py`: `bot.load_extension("cogs.my_feature")`

### Add a data model
1. Create file in `models/` extending `beanie.Document`
2. Define `Settings` with collection name and indexes
3. Initialize in `core/bot.py` `on_ready()`: Add to `init_beanie(..., document_models=[...])`

### Add a modal for user input
1. Create file in `utils/modals/` extending `discord.ui.Modal`
2. Add inputs with `self.add_item()`
3. Implement `async def callback(interaction)` for submission
4. Instantiate and send: `await ctx.send_modal(MyModal())`

### Add a persistent view (buttons)
1. Create file in `utils/views/` extending `discord.ui.View`
2. Define buttons with `@discord.ui.button(custom_id="...")`
3. Send with view: `await message.send(view=MyView())`

## Key Conventions & Notable Patterns

- **Cog initialization**: `core.Cog` provides `self.bot` and `self.redis` automatically
- **Config access**: Global `config` dict from TOML, not environment variables
- **Beanie over raw PyMongo**: Full ORM with type safety and validation
- **Guild-restricted cogs**: Specify at cog class level, not per-command
- **Embed customization**: Pre-styled subclasses (`SuccessEmbed`, `ErrorEmbed`)
- **Async throughout**: All Discord, Redis, and MongoDB operations require `await`
- **ID handling**: Store Discord IDs as strings in MongoDB, convert to int when fetching

## Debugging Quick Reference

- **Logs**: Check `qadir.log` for debug output (set `APP_DEBUG=true` for verbose)
- **Bot readiness**: Bot blocks on `_initialised` event until fully loaded
- **View persistence**: Requires `custom_id` and `timeout=None`
- **Slow queries**: Check MongoDB indexes in ARCHITECTURE.md

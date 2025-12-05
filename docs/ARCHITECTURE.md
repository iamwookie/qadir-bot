# Qadir Bot - Architecture

## Project Overview
Qadir is a modular Discord bot built with **Pycord** that provides utility, proposal voting, event/loot tracking, hangar management, and voice channel features. It uses **MongoDB + Beanie** for data persistence, **Upstash Redis** for caching, and modern Discord slash commands.

**Key Tech Stack:** Python 3.12.3 | Pycord (discord.py fork) | Beanie ODM | MongoDB | Upstash Redis | Poetry

## Core Structure

### Directory Layout
- **`core/bot.py`** - Custom `Qadir` Discord bot class extending `discord.Bot`. Initializes Redis, MongoDB, and manages the `_initialised` event. Auto-discovers and loads cogs on startup.
- **`cogs/`** - Feature modules (utility, proposals, events, hangar, voice). Each cog extends `core.Cog`, which wraps the bot instance and provides `self.redis` access.
- **`models/`** - **Beanie Document models** (not Pydantic BaseModels). Use `@Document` decorator with `Settings` for collection names and indexes. Examples: `Proposal`, `Event`, `HangarEmbedItem`.
- **`utils/`** - Shared utilities: custom embeds, modals, views, helpers, and enums.

### Component Interaction
```
main.py
  └─> Qadir (core/bot.py)
        ├─> Redis (Upstash)
        ├─> MongoDB (AsyncMongoClient)
        └─> Cogs (cogs/*.py)
              ├─> Models (models/*.py) ←─> MongoDB
              ├─> Views (utils/views/*.py)
              ├─> Modals (utils/modals/*.py)
              └─> Embeds (utils/embeds/*.py)
```

## Cog Architecture

**Every cog** inherits from `core.Cog` and optionally specifies `guild_ids` for guild-restricted commands:
```python
class MyFeatureCog(Cog, name="Feature Name", guild_ids=GUILD_IDS):
    def __init__(self, bot: Qadir):
        super().__init__(bot)
        # self.bot and self.redis are now available
```

### Task Loops
Cogs can define background tasks using `@tasks.loop()`. These must be started in `__init__()` and canceled in `cog_unload()`:
```python
@tasks.loop(hours=12)
async def _process_items(self) -> None:
    """Background task that runs every 12 hours."""
    pass

def __init__(self, bot: Qadir):
    super().__init__(bot)
    self._process_items.start()

def cog_unload(self):
    self._process_items.cancel()
```

Example implementations: `proposals.py` (_process_proposals), `events.py` (_restore_voting_views)

## Data Persistence

### MongoDB (Beanie Documents)
Models inherit from `beanie.Document` and define metadata via a nested `Settings` class:

```python
from datetime import datetime
from beanie import Document
from pydantic import Field
import discord

class MyModel(Document):
    thread_id: str
    created_at: datetime = Field(default_factory=discord.utils.utcnow)
    status: str
    
    class Settings:
        name = "my_collection"  # MongoDB collection name
        indexes = [
            "thread_id",
            "created_at",
            "status",
        ]
```

**Query patterns:**
```python
# Find multiple
items = await MyModel.find(MyModel.status == "active").to_list()

# Find one
item = await MyModel.find_one(MyModel.thread_id == str(thread_id))

# Count
count = await MyModel.count()

# Insert
await item.insert()

# Update (upsert)
await item.replace()

# Delete
await item.delete()
```

### Redis Caching Strategy
Use Redis for frequently-accessed data with short TTL. Always fall back to MongoDB on cache miss:

```python
REDIS_PREFIX = "qadir:events"
REDIS_TTL = 3600  # 1 hour

async def get_or_fetch_event(self, thread_id: int) -> Event | None:
    # Try cache first
    cached = await self.redis.get(f"{REDIS_PREFIX}:{thread_id}")
    if cached:
        return Event(**json.loads(cached))
    
    # Fall back to MongoDB
    event = await Event.find_one(Event.thread_id == str(thread_id))
    if event:
        # Populate cache
        await self.redis.set(
            f"{REDIS_PREFIX}:{thread_id}",
            json.dumps(event.model_dump(), default=str),
            ex=REDIS_TTL,
        )
        return event
    
    return None
```

**Cache invalidation:** Always delete from Redis when data changes:
```python
await event.replace()  # Update MongoDB
await self.redis.delete(f"{REDIS_PREFIX}:{event.thread_id}")  # Invalidate cache
```

## Discord UI Components

### Custom Embeds (`utils/embeds/`)
Pre-styled embed classes for consistency:
```python
class SuccessEmbed(discord.Embed):  # Green color
    def __init__(self, **kwargs) -> None:
        super().__init__(colour=discord.Colour.green(), **kwargs)

class ErrorEmbed(discord.Embed):    # Red color with defaults
    def __init__(self, title: str | None = "Uh Oh", description: str = "Something went wrong 😞", **kwargs) -> None:
        super().__init__(title=title, description=description, colour=discord.Colour.red(), **kwargs)
```

### Modals (`utils/modals/`)
User input forms. Extend `discord.ui.Modal`:
```python
class MyModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(title="Modal Title", *args, **kwargs)
        self.add_item(discord.ui.InputText(label="Field Name", max_length=100))
    
    async def on_error(self, error: Exception, interaction: discord.Interaction) -> None:
        logger.error("Modal error", exc_info=error)
        await interaction.followup.send(embed=ErrorEmbed(), ephemeral=True)
    
    async def callback(self, interaction: discord.Interaction):
        # Handle submission
        value = self.children[0].value
        await interaction.response.defer(ephemeral=True)
        # ... process data ...
```

### Views (`utils/views/`)
Persistent button handlers. Extend `discord.ui.View` with `timeout=None`:
```python
class MyView(discord.ui.View):
    def __init__(self, context_id: int) -> None:
        super().__init__(timeout=None)
        self.context_id = context_id
        self.model = None  # Lazy-load on first interaction
    
    async def on_error(self, error, _: discord.ui.Item, interaction: discord.Interaction) -> None:
        logger.error("View error", exc_info=error)
        await interaction.response.send_message(embed=ErrorEmbed(), ephemeral=True)
    
    @discord.ui.button(label="Button", style=discord.ButtonStyle.green, custom_id="my_button")
    async def my_button(self, _: discord.ui.Button, interaction: discord.Interaction):
        # Lazy-load model on first interaction to reduce memory
        if not self.model:
            self.model = await MyModel.find_one({"id": str(self.context_id)})
        
        await interaction.response.send_message("Button clicked!", ephemeral=True)
```

## Configuration

### Loading Configuration
`config.py` loads TypedDict-typed config from TOML files:
- **`config.toml`** - Production configuration
- **`config.dev.toml`** - Development configuration (copy from `config.toml` and customize)
- Environment determined by `PYTHON_ENV` env var (defaults to "development")

```python
from config import config

# Access config anywhere
guild_ids = config["proposals"]["guilds"]
channels = config["events"]["channels"]
```

### Environment Variables
Set in `.env` file:
```
DISCORD_TOKEN=your_token_here
MONGODB_URI=mongodb+srv://...
UPSTASH_REDIS_REST_URL=https://...
UPSTASH_REDIS_REST_TOKEN=...
APP_DEBUG=true
PYTHON_ENV=development
```

## Slash Commands

### Simple Command
```python
class MyCog(Cog, name="Feature"):
    @discord.slash_command(description="Do something")
    async def mycommand(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond("Done!")
```

### Guild-Restricted Command
```python
class ProposalsCog(Cog, name="Proposals", guild_ids=[123456789]):
    # All commands in this cog are restricted to guild 123456789
    
    @discord.slash_command(description="Vote on proposal")
    async def vote(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond("Voted!")
```

### Command Groups
```python
class EventsCog(Cog):
    event = discord.SlashCommandGroup("event", "Manage events")
    
    @event.command(description="Create event")
    async def create(self, ctx: discord.ApplicationContext) -> None:
        await ctx.send_modal(CreateEventModal())
    
    @event.command(description="Join event")
    async def join(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond("Joined!")
```

### Deferred Responses (Long Operations)
```python
@discord.slash_command()
async def expensive_operation(self, ctx: discord.ApplicationContext) -> None:
    await ctx.defer(ephemeral=True)  # Shows "Bot is thinking..."
    
    # Do long operation
    result = await some_expensive_query()
    
    await ctx.followup.send(f"Result: {result}", ephemeral=True)
```

## Enums (Status Flags)

Defined in `utils/enums.py` as `str` Enums for MongoDB compatibility:
```python
class ProposalStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"

class EventStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
```

Use for type-safe filtering:
```python
active = await Proposal.find(Proposal.status == ProposalStatus.ACTIVE).to_list()
```

## Error Handling

**Global error handler** in `core/bot.py`:
```python
async def on_application_command_error(self, ctx: discord.ApplicationContext, exception: Exception) -> None:
    if isinstance(exception, CheckFailure):
        await ctx.respond(embed=ErrorEmbed("Permission Denied"), ephemeral=True)
    elif isinstance(exception, CommandOnCooldown):
        await ctx.respond(embed=ErrorEmbed("On Cooldown", f"Try again in {exception.retry_after:.2f}s"), ephemeral=True)
```

**Per-cog error handler:**
```python
class MyCog(Cog):
    async def on_error(self, exception: Exception, ctx: discord.ApplicationContext) -> None:
        logger.error("Cog error", exc_info=exception)
        await ctx.respond(embed=ErrorEmbed(), ephemeral=True)
```

**Modal/View error handlers:**
```python
async def on_error(self, error: Exception, interaction: discord.Interaction) -> None:
    logger.error("Component error", exc_info=error)
    await interaction.response.send_message(embed=ErrorEmbed(), ephemeral=True)
```

Common exceptions:
- `discord.NotFound` - Resource no longer exists
- `discord.Forbidden` - Missing permissions
- `CheckFailure` - Permission check failed
- `CommandOnCooldown` - Command in cooldown

## Utilities

### Timestamp Helpers (`utils/common.py`)
```python
from utils import dt_to_psx, psx_to_dt
from datetime import datetime
import discord

# Convert datetime → Unix timestamp
ts = dt_to_psx(discord.utils.utcnow())

# Convert Unix timestamp → datetime
dt = psx_to_dt(1234567890.0)
```

### ID Handling Convention
Discord IDs are **always stored as strings** in MongoDB for consistency:
```python
# When storing
proposal = Proposal(
    creator_id=str(interaction.user.id),
    thread_id=str(thread.id),
)

# When fetching Discord objects
user = await bot.get_or_fetch(discord.User, int(proposal.creator_id))
thread = await bot.get_or_fetch(discord.Thread, int(proposal.thread_id))
```

## Logging

**Logger name:** `"qadir"` (configured in `main.py`)

**Log levels:**
- `DEBUG` - Enabled when `APP_DEBUG=true`
- `INFO` - Default level
- `WARNING` - Warnings and higher
- `ERROR` - Errors with full traceback

**Output:**
- Console: INFO+ (or DEBUG if `APP_DEBUG=true`)
- File (`qadir.log`): DEBUG always

**Usage in cogs:**
```python
import logging
logger = logging.getLogger("qadir")

logger.debug("Detailed info for debugging")
logger.info("General operation info")
logger.warning("Something unexpected")
logger.exception("Exception with traceback")  # Use in except blocks
```

## Data Flow Example: Proposal Voting

1. **Command**: User runs `/proposal create` (UtilityCog)
2. **Modal**: `CreateProposalModal` opens for user input
3. **Modal Callback**: Creates thread, sends embeds, stores in MongoDB via `Proposal.insert()`
4. **View**: `VotingView` buttons attached to message with `custom_id="upvote"` / `custom_id="downvote"`
5. **Button Click**: Button handler fetches `Proposal` from MongoDB (lazy-load), updates votes, calls `proposal.replace()`
6. **Background Task**: `_process_proposals` loop (12-hour interval) checks for 24h+ old proposals, closes them
7. **Cleanup**: `on_error()` handles missing threads/messages, deletes stale MongoDB records

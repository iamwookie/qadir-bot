# Qadir Bot - Code Review & Suggestions

This document contains ranked suggestions for improving code practices, security, and maintainability. Use this as a reference for enhancement opportunities and as a checklist for implementation priorities.

---

## 🔴 CRITICAL (Security/Stability)

### 1. **Missing Error Handling in CreateEventModal.on_error() Parameters**
**File:** `utils/modals/create_event.py` (lines 13-14)

**Issue:** The `on_error()` method signature is incorrect - Pycord passes parameters in the wrong order in type hints. The implementation has correct handling but the parameter order should be consistent.

**Current:**
```python
async def on_error(self, _: discord.Interaction, error: Exception) -> None:
```

**Recommended:**
```python
async def on_error(self, error: Exception, interaction: discord.Interaction) -> None:
    logger.error("[MODAL] CreateEventModal Error", exc_info=error)
    await interaction.followup.send(embed=ErrorEmbed(), ephemeral=True)
```

**Impact:** High - Silent failures in modal submissions, users won't know if their action failed.

---

### 2. **Hardcoded Developer ID in UtilityCog**
**File:** `cogs/utility.py` (line 36)

**Issue:** Developer ID `244662779745665026` is hardcoded, making the codebase exposed and difficult to maintain.

**Current:**
```python
dev_id = 244662779745665026
```

**Recommended:**
```python
# In config.toml / config.dev.toml
[app]
developer_id = 244662779745665026

# In cog
dev_id = config["app"]["developer_id"]
```

**Impact:** High - Security exposure, inflexible configuration.

---

### 3. **Unsafe Integer Conversion Without Try-Except in Multiple Places**
**Files:** 
- `utils/views/voting.py` (line 48)
- `cogs/events.py` (line 42, 177)
- `utils/modals/create_event.py` (line 80)

**Issue:** Direct type casting `int(proposal.thread_id)` without error handling can cause crashes if data is corrupted.

**Example:**
```python
# Current - unsafe
thread = await self.bot.get_or_fetch(discord.Thread, int(proposal.thread_id))

# Recommended
try:
    thread_id = int(proposal.thread_id)
    thread = await self.bot.get_or_fetch(discord.Thread, thread_id)
except (ValueError, discord.NotFound, discord.Forbidden) as e:
    logger.error(f"Failed to fetch thread {proposal.thread_id}", exc_info=e)
    return None
```

**Impact:** High - Silent crashes, corrupted data handling.

---

### 4. **Unbounded Quantity Validation in AddLootModal**
**File:** `utils/modals/add_loot.py` (lines 80-82)

**Issue:** Quantity validation allows up to 1 billion items, which could lead to integer overflow or database issues.

**Current:**
```python
if quantity <= 0 or quantity >= 1000000000:
    raise ValueError("Quantity out of range")
```

**Recommended:**
```python
MAX_QUANTITY = 1_000_000  # 1 million max per entry
if quantity <= 0 or quantity > MAX_QUANTITY:
    embed = ErrorEmbed("Invalid Quantity", f"Please enter a number between `1` and `{MAX_QUANTITY:,}`.")
    await interaction.followup.send(embed=embed, ephemeral=True)
    return
```

**Impact:** Medium - Potential DoS via database bloat, data integrity issues.

---

### 5. **Missing Null Check for User Avatar in EventEmbed**
**File:** `cogs/events.py` (line 83-86)

**Issue:** If `creator.display_avatar` is None, the code will crash. No null coalescing.

**Current:**
```python
event_embed.set_footer(text=f"Created by {creator}", icon_url=creator.display_avatar.url)
```

**Recommended:**
```python
avatar_url = creator.display_avatar.url if creator.display_avatar else None
event_embed.set_footer(text=f"Created by {creator}", icon_url=avatar_url)
```

**Impact:** Medium - Potential crash on event card updates.

---

## 🟠 HIGH (Performance/Best Practices)

### 6. **Inefficient Event Filtering in EventsCog.join()**
**File:** `cogs/events.py` (lines 173-175)

**Issue:** Filters are applied in Python memory after fetching all events. Should use MongoDB query directly.

**Current:**
```python
active_events = await Event.find(Event.status == EventStatus.ACTIVE).to_list()
joinable_events = [event for event in active_events if str(ctx.author.id) not in event.participants]
```

**Recommended:**
```python
# Use MongoDB aggregation or multiple queries
joinable_events = await Event.find({
    "status": EventStatus.ACTIVE,
    "participants": {"$nin": [str(ctx.author.id)]}
}).to_list()
```

**Impact:** High - N+1 query pattern, poor scalability with many events.

---

### 7. **Missing Proposal Cache Invalidation in VotingView**
**File:** `utils/views/voting.py` (lines 68-69, 96-97)

**Issue:** Comments mention "Redis" but no actual Redis cache invalidation occurs. Cached data could become stale.

**Current:**
```python
# Update Redis with new vote data
await self.proposal.replace()  # Only MongoDB updated, Redis not invalidated
```

**Recommended:**
```python
# Update MongoDB and invalidate cache
await self.proposal.replace()
# Invalidate cache if using Redis
# await self.redis.delete(f"qadir:proposals:{self.proposal.thread_id}")
```

**Impact:** High - Stale cache data if Redis is implemented later.

---

### 8. **N+1 Query in HangarCog._process_hangar_embeds**
**File:** `cogs/hangar.py` (lines 275+)

**Issue:** The hangar processing likely fetches embeds one-by-one in a loop instead of batch operations.

**Impact:** High - Scalability bottleneck as number of hangar embeds grows.

---

### 9. **Missing Context Manager for Database Connections**
**File:** `core/bot.py` (lines 32-34)

**Issue:** MongoDB connections are never explicitly closed. Memory leaks possible in long-running bots.

**Current:**
```python
self.mongo: AsyncMongoClient = AsyncMongoClient(MONGODB_URI)
```

**Recommended:**
```python
async def close(self) -> None:
    """Close database connections on shutdown."""
    if hasattr(self, 'mongo'):
        self.mongo.close()
    await super().close()
```

**Impact:** High - Memory leak on bot restart/reload.

---

### 10. **Inefficient Redis Pipeline Usage**
**File:** `utils/views/event_selection.py` (line 71-75)

**Issue:** Uses `pipeline()` but `.exec()` returns results that are ignored. Could be single async operations.

**Current:**
```python
pipeline = self.redis.pipeline()
pipeline.delete(f"{self.cog.REDIS_PREFIX}:{str(selected_thread_id)}")
pipeline.delete(f"{self.cog.REDIS_PREFIX}:active")
pipeline.delete(f"{self.cog.REDIS_PREFIX}:user:{interaction.user.id}")
await pipeline.exec()
```

**Recommended:** If only deleting, use batch operations or individual deletes with better error handling.

**Impact:** Medium - Unnecessary complexity, minor performance overhead.

---

## 🟡 MEDIUM (Code Quality & Maintainability)

### 11. **Magic Numbers Throughout HangarCog**
**File:** `cogs/hangar.py` (lines 45-57)

**Issue:** Durations and thresholds are hardcoded. Makes configuration changes difficult.

**Current:**
```python
_OPEN_DURATION: int = 3900417
_CLOSE_DURATION: int = 7200771
_THRESHOLDS: list[dict] = [...]
```

**Recommended:**
```python
# Load from config.toml
_OPEN_DURATION = config["hangar"]["open_duration_ms"]
_CLOSE_DURATION = config["hangar"]["close_duration_ms"]
_THRESHOLDS = config["hangar"]["light_thresholds"]
_INITIAL_OPEN_TIME = datetime.fromisoformat(config["hangar"]["initial_open_time"])
```

**Impact:** Medium - Reduces flexibility and increases maintenance burden.

---

### 12. **Unused Imports**
**Files:**
- `cogs/events.py` - `json` imported but only used in caching (line 8)
- `utils/views/event_selection.py` - `json` imported but not used (check line 5)

**Impact:** Low - Code cleanliness, unused dependencies confuse readers.

---

### 13. **Inconsistent Type Hints for Cog Initialization**
**Files:**
- `cogs/events.py` (line 27) - `def __init__(self, bot):` should be `def __init__(self, bot: Qadir):`
- `cogs/voice.py` (line 18) - Same issue

**Impact:** Medium - Type safety, IDE autocomplete, documentation.

---

### 14. **Repeated Redis Key Construction**
**Files:**
- `cogs/events.py` (lines 50, 54, 56, 131, 156, 177)
- `cogs/hangar.py` (multiple references to `_REDIS_PREFIX`)

**Issue:** Redis keys built ad-hoc instead of using centralized helper function.

**Recommended:**
```python
class EventsCog(Cog):
    def _cache_key(self, key: str) -> str:
        return f"{self.REDIS_PREFIX}:{key}"
    
    async def get_or_fetch_event(self, thread_id: int):
        cached = await self.redis.get(self._cache_key(str(thread_id)))
```

**Impact:** Medium - DRY principle, easier to rename/refactor.

---

### 15. **Missing Docstrings in Critical Methods**
**Files:**
- `cogs/voice.py` - `_connect_to_channel()` has docstring but no parameter docs
- `utils/embeds/event.py` - `loot_distribution()` method missing docstring

**Impact:** Low - Documentation, maintainability.

---

### 16. **Inconsistent Error Message Formatting**
**Throughout:** Some errors use `embed=ErrorEmbed()`, others use `embed=ErrorEmbed(title="...", description="...")`

**Recommended:** Create standardized error response helper:
```python
async def error_response(ctx, title: str, description: str) -> None:
    await ctx.followup.send(embed=ErrorEmbed(title=title, description=description), ephemeral=True)
```

**Impact:** Low - Code consistency, easier bulk updates.

---

## 🔵 LOW (Enhancement Opportunities)

### 17. **Consider Adding Request Rate Limiting**
**File:** `cogs/utility.py` (line 151)

**Issue:** Only the `find` command has cooldown. Other commands could benefit from rate limiting to prevent abuse.

**Recommended:**
```python
@discord.slash_command()
@commands.cooldown(3, 60.0, commands.BucketType.user)  # 3 per 60 seconds per user
async def propose(self, ctx: discord.ApplicationContext) -> None:
```

**Impact:** Low - Feature enhancement, user protection.

---

### 18. **Add Logging for Proposal Processing Loop Completion**
**File:** `cogs/proposals.py` (line 106)

**Issue:** No log when no proposals exist, making it hard to debug in production.

**Current:**
```python
if not proposals:
    logger.debug("⌛✅️ [PROPOSALS] [0] No Proposals To Process")
    return
```

**Recommended:** Keep as-is, but ensure debug logging is enabled in production for monitoring.

**Impact:** Low - Observability improvement.

---

### 19. **Add Configuration Validation on Startup**
**File:** `config.py`

**Issue:** No validation that required config keys exist before bot starts.

**Recommended:**
```python
def validate_config(config: Config) -> None:
    required_keys = ["app", "proposals", "events", "hangar", "voice"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
```

**Impact:** Low - Better error messages, faster debugging.

---

### 20. **Consider Adding Metrics/Telemetry**
**General Suggestion**

**Issue:** No way to track bot performance (response times, error rates, cache hit rates).

**Recommended:** Add prometheus metrics or similar:
```python
from prometheus_client import Counter, Histogram

proposal_votes = Counter('proposals_votes_total', 'Total votes', ['vote_type'])
command_latency = Histogram('command_latency_seconds', 'Command response time')
```

**Impact:** Low - Production monitoring, performance analysis.

---

## Summary Table

| Priority | Category | Count | Examples |
|----------|----------|-------|----------|
| 🔴 Critical | Security/Stability | 5 | Error handling, hardcoded IDs, unsafe casting |
| 🟠 High | Performance/Best Practices | 5 | Query optimization, cache invalidation, connections |
| 🟡 Medium | Code Quality | 5 | Type hints, magic numbers, repeated code |
| 🔵 Low | Enhancements | 5 | Rate limiting, logging, metrics |

---

## Recommended Implementation Order

1. **Immediate (Critical Security):**
   - Fix CreateEventModal error handler
   - Remove hardcoded developer ID
   - Add try-except to integer conversions

2. **High Priority (Performance):**
   - Implement proper MongoDB query filtering
   - Add connection cleanup in bot shutdown
   - Fix cache invalidation

3. **Medium Priority (Code Quality):**
   - Add missing type hints
   - Consolidate Redis key construction
   - Remove unused imports

4. **Low Priority (Enhancements):**
   - Add rate limiting
   - Implement configuration validation
   - Add telemetry/monitoring

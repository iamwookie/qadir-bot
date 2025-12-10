# Qadir Bot - Code Review & Suggestions

This document contains ranked suggestions for improving code practices, security, and maintainability. Use this as a reference for enhancement opportunities and as a checklist for implementation priorities.

---

## 🔴 CRITICAL (Security/Stability)

### 1. **Hardcoded Developer ID in UtilityCog**
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

### 2. **Unsafe Integer Conversion Without Try-Except in ProposalsCog**
**File:** `cogs/proposals.py` (lines 66-150)

**Issue:** Directly casting `proposal.thread_id` to `int` when fetching threads/messages can raise `ValueError` if data is corrupted and can mask Discord API errors.

**Current:**
```python
thread = await self.bot.get_or_fetch(discord.Thread, int(proposal.thread_id))
message = thread.get_partial_message(int(proposal.message_id))
```

**Recommended:**
```python
try:
    thread_id = int(proposal.thread_id)
    message_id = int(proposal.message_id)
    thread = await self.bot.get_or_fetch(discord.Thread, thread_id)
    message = thread.get_partial_message(message_id)
except (ValueError, discord.NotFound, discord.Forbidden) as exc:
    logger.error("[PROPOSALS] Failed to fetch proposal thread/message", exc_info=exc)
    await proposal.delete()
    return
```

**Impact:** High - Prevents crashes and cleans up corrupted records safely.

---

## 🟠 HIGH (Performance/Best Practices)

### 3. **Missing Proposal Cache Invalidation in VotingView**
**File:** `utils/views/voting.py` (vote handlers)

**Issue:** Comments reference Redis but no cache invalidation occurs after vote updates. Cached proposals (if added later) would become stale.

**Recommended:**
```python
await self.proposal.replace()
# If Redis caching is enabled:
# await self.redis.delete(f"qadir:proposals:{self.proposal.thread_id}")
```

**Impact:** High - Avoids serving stale vote counts when caching is introduced.

---

### 4. **N+1 Query in HangarCog._process_hangar_embeds**
**File:** `cogs/hangar.py` (lines 275+)

**Issue:** Hangar embed processing likely fetches items one-by-one instead of batching.

**Impact:** High - Scalability bottleneck as hangar item count grows.

---

### 5. **Missing Context Manager for Database Connections**
**File:** `core/bot.py` (Mongo client lifecycle)

**Issue:** MongoDB connections are never explicitly closed; reloads can leak sockets.

**Recommended:**
```python
async def close(self) -> None:
    if hasattr(self, "mongo"):
        self.mongo.close()
    await super().close()
```

**Impact:** High - Prevents connection leaks during shutdown/restart.

---

## 🟡 MEDIUM (Code Quality & Maintainability)

### 6. **Magic Numbers Throughout HangarCog**
**File:** `cogs/hangar.py` (lines 45-57)

**Issue:** Durations and thresholds are hardcoded, making tuning difficult.

**Recommendation:** Load from config (e.g., `config["hangar"]["open_duration_ms"]`, etc.) and document expected units.

**Impact:** Medium - Improves configurability and readability.

---

### 7. **Inconsistent Type Hints for Cog Initialization**
**File:** `cogs/voice.py` (line 18)

**Issue:** `__init__` lacks a `Qadir` type hint for the bot parameter, reducing IDE assistance.

**Recommended:**
```python
def __init__(self, bot: Qadir) -> None:
    super().__init__(bot)
```

**Impact:** Medium - Better type safety and editor support.

---

### 8. **Repeated Redis Key Construction**
**File:** `cogs/hangar.py`

**Issue:** Redis keys are built ad-hoc, making refactors error-prone.

**Recommended:** Centralize with a helper like `self._cache_key(key: str) -> str` and reuse everywhere.

**Impact:** Medium - DRY and safer key changes.

---

### 9. **Inconsistent Error Message Formatting**
**Scope:** Mixed use of `ErrorEmbed()` defaults vs. custom titles/descriptions.

**Recommended:** Add a helper (e.g., `error_response(ctx, title, description)`) to keep user-facing errors consistent.

**Impact:** Low-Medium - Cleaner UX and easier updates.

---

## 🔵 LOW (Enhancement Opportunities)

### 10. **Consider Adding Request Rate Limiting**
**File:** `cogs/utility.py` (most commands)

**Issue:** Only `find` uses cooldown. Adding light rate limits protects against spam.

**Recommended:** Apply `@commands.cooldown` per-user for other high-traffic commands.

**Impact:** Low - Abuse prevention.

---

### 11. **Add Configuration Validation on Startup**
**File:** `config.py`

**Issue:** No validation that required config keys exist before boot.

**Recommended:**
```python
def validate_config(config: Config) -> None:
    required_keys = ["app", "proposals", "hangar", "voice"]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required config key: {key}")
```

**Impact:** Low - Fails fast on misconfiguration.

---

### 12. **Consider Adding Metrics/Telemetry**
**General Suggestion**

**Issue:** No visibility into command latency, errors, or cache hit rates.

**Recommended:** Add Prometheus counters/histograms for proposals, command latency, and cache usage.

**Impact:** Low - Improves observability for production.

---

## Summary Table

| Priority | Category | Count | Examples |
|----------|----------|-------|----------|
| 🔴 Critical | Security/Stability | 2 | Hardcoded IDs, unsafe casting |
| 🟠 High | Performance/Best Practices | 3 | Cache invalidation, query efficiency, connection cleanup |
| 🟡 Medium | Code Quality | 4 | Config-driven values, type hints, Redis keys, error formatting |
| 🔵 Low | Enhancements | 3 | Rate limiting, config validation, telemetry |

---

## Recommended Implementation Order

1. **Immediate (Critical Security):**
   - Remove hardcoded developer ID
   - Add try-except around proposal thread/message lookups

2. **High Priority (Performance):**
   - Add cache invalidation hook for proposal votes
   - Batch hangar embed processing
   - Close Mongo connections on shutdown

3. **Medium Priority (Code Quality):**
   - Move hangar tuning values to config
   - Add missing type hints and Redis key helper
   - Standardize error responses

4. **Low Priority (Enhancements):**
   - Add rate limiting
   - Implement configuration validation
   - Add telemetry/monitoring

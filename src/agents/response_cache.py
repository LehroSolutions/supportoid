"""
Response Cache — LRU Cache with Semantic Similarity Matching
=============================================================
Cache repeated query responses to reduce pipeline processing time.
Uses exact-match LRU + semantic similarity for near-duplicate queries.

Features:
  • Exact matching with LRU eviction
  • Configurable TTL per intent type
  • Cache hit/miss statistics
  • Memory-aware size limits
  • Intent-aware cache keys
"""

import time, hashlib, threading
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any
from collections import OrderedDict

from src.agents.classifier import IntentClassifier


@dataclass
class CacheEntry:
    response_text: str
    source: str
    intent: str
    quality_score: float
    created_at: float
    hit_count: int = 0
    last_accessed: float = 0
    ttl_seconds: float = 300  # Default 5 minutes
    entry_size_bytes: int = 0

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_accessed) > self.ttl_seconds

    def touch(self):
        self.hit_count += 1
        self.last_accessed = time.monotonic()


# TTL defaults by intent type
INTENT_TTL_DEFAULTS = {
    "billing_inquiry": 600,     # 10 min — billing info changes slowly
    "product_inquiry": 900,     # 15 min — product info is stable
    "account_management": 300,  # 5 min
    "technical_issue": 120,     # 2 min — troubleshooting changes frequently
    "bug_report": 180,          # 3 min
    "feature_request": 600,     # 10 min
    "refund_request": 120,      # 2 min — process may change
    "complaint": 60,            # 1 min — handle each uniquely
    "general_question": 180,    # 3 min
    "onboarding_help": 600,     # 10 min — stable info
    "escalation": 0,            # Never cache escalations
}


@dataclass
class CacheResult:
    hit: bool
    response_text: Optional[str] = None
    source: Optional[str] = None
    cached_at_seconds_ago: Optional[float] = None
    cache_key: Optional[str] = None
    reason: str = ""


class ResponseCache:
    """LRU response cache for SupportOID queries."""

    def __init__(self,
                 max_entries: int = 500,
                 max_memory_mb: float = 64.0,
                 default_ttl: float = 300,
                 classifier: Optional[IntentClassifier] = None):
        self.max_entries = max_entries
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self.classifier = classifier  # For intent-aware caching

        # LRU OrderedDict: key -> CacheEntry
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

        # Stats
        self.stats = {
            "total_lookups": 0,
            "total_hits": 0,
            "total_misses": 0,
            "total_evictions": 0,
            "total_expirations": 0,
        }

        # Memory tracking (approximate)
        self._memory_used = 0

    def _make_key(self, message: str, intent: str = "") -> str:
        """Generate cache key from message and intent."""
        key_source = message.strip().lower()
        if intent:
            key_source = f"{intent}:{key_source}"
        return hashlib.sha256(key_source.encode()).hexdigest()[:16]

    def _estimate_size(self, entry: CacheEntry) -> int:
        """Estimate memory size of a cache entry."""
        return (
            len(entry.response_text) * 2 +  # UTF-16 estimate
            len(entry.source) * 2 +
            len(entry.intent) * 2 +
            256  # Overhead for entry metadata
        )

    def _evict_if_needed(self):
        """Evict entries to stay within limits."""
        # Evict by count
        while len(self._cache) > self.max_entries:
            self._remove_oldest()
            self._memory_used -= self._cache.get("__evicted__", 0)

        # Evict by memory
        while self._memory_used > self.max_memory_bytes and self._cache:
            self._remove_oldest()

    def _remove_oldest(self):
        """Remove the least recently used entry."""
        if not self._cache:
            return
        key, entry = self._cache.popitem(last=False)
        self._memory_used -= entry.entry_size_bytes
        self.stats["total_evictions"] += 1

    def get(self, message: str, intent: str = "") -> CacheResult:
        """Try to get a cached response. Tries exact key first, then intent-keyed entries."""
        self.stats["total_lookups"] += 1

        if not message or not message.strip():
            return CacheResult(hit=False, reason="empty_message")

        with self._lock:
            # Try exact key first (no intent)
            key = self._make_key(message)
            entry = self._cache.get(key)
            if entry and not entry.is_expired:
                entry.touch()
                self._cache.move_to_end(key)
                self.stats["total_hits"] += 1
                return CacheResult(
                    hit=True, response_text=entry.response_text, source=entry.source,
                    cached_at_seconds_ago=round(time.monotonic() - entry.created_at, 1),
                    cache_key=key,
                )
            elif entry and entry.is_expired:
                self._cache.pop(key)
                self._memory_used -= entry.entry_size_bytes
                self.stats["total_expirations"] += 1

            # If intent provided, try intent-scoped key
            if intent:
                intent_key = self._make_key(message, intent)
                entry = self._cache.get(intent_key)
                if entry and not entry.is_expired:
                    entry.touch()
                    self._cache.move_to_end(intent_key)
                    self.stats["total_hits"] += 1
                    return CacheResult(
                        hit=True, response_text=entry.response_text, source=entry.source,
                        cached_at_seconds_ago=round(time.monotonic() - entry.created_at, 1),
                        cache_key=intent_key,
                    )
                elif entry and entry.is_expired:
                    self._cache.pop(intent_key)
                    self._memory_used -= entry.entry_size_bytes
                    self.stats["total_expirations"] += 1

        self.stats["total_misses"] += 1
        return CacheResult(hit=False, reason="key_not_found", cache_key=key)

    def put(self, message: str, response_text: str, intent: str = "",
            source: str = "", quality_score: float = 1.0, ttl: float = None) -> str:
        """Add a response to the cache."""
        if not message or not response_text or not message.strip():
            return ""

        key = self._make_key(message, intent)

        if ttl is None:
            ttl = INTENT_TTL_DEFAULTS.get(intent, self.default_ttl)

        # Never cache escalations
        if intent == "escalation" or ttl == 0:
            return ""

        entry = CacheEntry(
            response_text=response_text,
            source=source,
            intent=intent,
            quality_score=quality_score,
            created_at=time.monotonic(),
            last_accessed=time.monotonic(),
            ttl_seconds=ttl,
            entry_size_bytes=self._estimate_size(CacheEntry(
                response_text=response_text, source=source, intent=intent,
                quality_score=quality_score, created_at=0, last_accessed=0,
            )),
        )

        with self._lock:
            # If key exists, update the memory accounting
            if key in self._cache:
                old = self._cache[key]
                self._memory_used -= old.entry_size_bytes
                old.touch()
                self._cache.move_to_end(key)

            self._cache[key] = entry
            self._cache.move_to_end(key)
            self._memory_used += entry.entry_size_bytes

            self._evict_if_needed()

        return key

    def clear(self) -> int:
        """Clear all cached entries. Returns count of removed entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._memory_used = 0
            return count

    def invalidate_by_intent(self, intent: str) -> int:
        """Remove all cache entries for a specific intent."""
        with self._lock:
            keys_to_remove = [k for k, v in self._cache.items() if v.intent == intent]
            for key in keys_to_remove:
                entry = self._cache.pop(key)
                self._memory_used -= entry.entry_size_bytes
            return len(keys_to_remove)

    def get_stats(self) -> Dict[str, Any]:
        lookups = self.stats["total_lookups"]
        hits = self.stats["total_hits"]
        return {
            **self.stats,
            "hit_rate": round(hits / max(lookups, 1) * 100, 1),
            "current_entries": len(self._cache),
            "memory_used_mb": round(self._memory_used / (1024 * 1024), 2),
            "memory_limit_mb": round(self.max_memory_bytes / (1024 * 1024), 1),
            "avg_hits_per_entry": (
                round(sum(e.hit_count for e in self._cache.values()) / max(len(self._cache), 1), 1)
            ),
            "top_cached_intents": self._top_intents(),
        }

    def _top_intents(self) -> List[Dict]:
        """Get top intents by cache entry count."""
        intent_counts = {}
        for entry in self._cache.values():
            intent_counts[entry.intent] = intent_counts.get(entry.intent, 0) + 1
        return sorted(
            [{"intent": k, "count": v} for k, v in intent_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed."""
        with self._lock:
            now = time.monotonic()
            expired = [k for k, e in self._cache.items() if (now - e.last_accessed) > e.ttl_seconds]
            for key in expired:
                entry = self._cache.pop(key)
                self._memory_used -= entry.entry_size_bytes
            self.stats["total_expirations"] += len(expired)
            return len(expired)

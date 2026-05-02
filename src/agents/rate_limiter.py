"""
Rate Limiter — Per-User Configurable Sliding Window
====================================================
Token-bucket + sliding-window hybrid rate limiter for SupportOID.
Supports configurable windows, multiple tiers, and burst allowance.

Features:
  • Sliding window counter with configurable window sizes
  • Per-user / per-IP tracking
  • Tier-based rate limits (free, pro, enterprise)
  • Burst allowance (short-term overage with penalty)
  • Automatic cleanup of expired entries
"""

import time, threading, logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

logger = logging.getLogger("supportoid.rate_limiter")


@dataclass
class RateLimitConfig:
    """Configuration for a single rate limit rule."""
    max_requests: int           # Max requests in window
    window_seconds: float       # Window duration
    burst_allowance: int = 0    # Extra requests allowed in a short burst
    burst_window_seconds: float = 10.0  # Burst window duration
    cooldown_seconds: float = 0.0       # Cooldown after exceeding limit
    block_after_cooldown: bool = False   # Block user after cooldown expires


# Predefined tier configurations
TIER_CONFIGS = {
    "free": {
        "requests": RateLimitConfig(max_requests=30, window_seconds=60, burst_allowance=5, burst_window_seconds=10, cooldown_seconds=30),
        "concurrent": RateLimitConfig(max_requests=3, window_seconds=60),
    },
    "pro": {
        "requests": RateLimitConfig(max_requests=120, window_seconds=60, burst_allowance=20, burst_window_seconds=15, cooldown_seconds=15),
        "concurrent": RateLimitConfig(max_requests=10, window_seconds=60),
    },
    "enterprise": {
        "requests": RateLimitConfig(max_requests=500, window_seconds=60, burst_allowance=100, burst_window_seconds=30, cooldown_seconds=5),
        "concurrent": RateLimitConfig(max_requests=50, window_seconds=60),
    },
}


@dataclass
class RateLimitResult:
    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_after_seconds: float
    retry_after_seconds: float
    tier: str
    burst_used: bool
    in_cooldown: bool
    flags: list = field(default_factory=list)


class SlidingWindowCounter:
    """Thread-safe sliding window counter using sub-window buckets."""

    def __init__(self, window_seconds: float, num_buckets: int = 10):
        self.window_seconds = window_seconds
        self.bucket_duration = window_seconds / num_buckets
        self.num_buckets = num_buckets
        self.buckets: list = [0] * num_buckets
        self.lock = threading.Lock()

    def add(self, count: int = 1) -> int:
        now = time.monotonic()
        with self.lock:
            self._prune()
            idx = self._bucket_index(now)
            self.buckets[idx] += count
            return sum(self.buckets)

    def count(self) -> int:
        now = time.monotonic()
        with self.lock:
            self._prune()
            return sum(self.buckets)

    def oldest_request_age(self) -> float:
        """Approximate age of oldest request in window."""
        now = time.monotonic()
        with self.lock:
            self._prune()
            # Check backwards from current bucket
            curr = self._bucket_index(now)
            for i in range(self.num_buckets):
                idx = (curr - i) % self.num_buckets
                if self.buckets[idx] > 0:
                    return i * self.bucket_duration
            return 0

    def reset(self):
        with self.lock:
            for i in range(self.num_buckets):
                self.buckets[i] = 0

    def _prune(self):
        now = time.monotonic()
        curr = self._bucket_index(now)
        # Zero out buckets outside the window
        for i in range(self.num_buckets):
            idx = (curr - i) % self.num_buckets
            if i * self.bucket_duration >= self.window_seconds:
                self.buckets[idx] = 0

    def _bucket_index(self, now: float) -> int:
        return int(now / self.bucket_duration) % self.num_buckets


class UserRateLimiter:
    """Per-user rate limiter with configurable tiers and burst support."""

    def __init__(self, default_tier: str = "free"):
        self.default_tier = default_tier
        self.user_tiers: Dict[str, str] = {}
        self.request_counters: Dict[str, SlidingWindowCounter] = {}
        self.burst_counters: Dict[str, SlidingWindowCounter] = {}
        self.cooldown_until: Dict[str, float] = {}
        self.lock = threading.Lock()
        self.stats = {
            "total_requests": 0,
            "total_blocked": 0,
            "total_burst_used": 0,
            "total_cooldown_triggered": 0,
        }

    def set_user_tier(self, user_id: str, tier: str):
        """Set the rate limit tier for a user."""
        with self.lock:
            self.user_tiers[user_id] = tier

    def get_tier(self, user_id: str) -> str:
        with self.lock:
            return self.user_tiers.get(user_id, self.default_tier)

    def check(self, user_id: str = "anonymous", tier: str = None) -> RateLimitResult:
        """Check if a request from user_id is allowed."""
        tier = tier or self.get_tier(user_id)
        tier_config = TIER_CONFIGS.get(tier, TIER_CONFIGS["free"])
        rl_config = tier_config["requests"]

        with self.lock:
            # Initialize counters for this user if needed
            if user_id not in self.request_counters:
                self.request_counters[user_id] = SlidingWindowCounter(rl_config.window_seconds)
            if user_id not in self.burst_counters:
                self.burst_counters[user_id] = SlidingWindowCounter(
                    rl_config.burst_window_seconds, num_buckets=5
                )

        self.stats["total_requests"] += 1

        # Check cooldown
        now = time.monotonic()
        with self.lock:
            cooldown_end = self.cooldown_until.get(user_id, 0)

        if cooldown_end > now:
            self.stats["total_blocked"] += 1
            return RateLimitResult(
                allowed=False,
                current_count=rl_config.max_requests,
                limit=rl_config.max_requests,
                remaining=0,
                reset_after_seconds=round(cooldown_end - now, 1),
                retry_after_seconds=round(cooldown_end - now, 1),
                tier=tier,
                burst_used=False,
                in_cooldown=True,
                flags=["cooldown_active"],
            )

        # Get current counts
        current_count = self.request_counters[user_id].count()
        burst_count = self.burst_counters[user_id].count()

        remaining = max(0, rl_config.max_requests - current_count)

        # Within normal limit → allow
        if current_count < rl_config.max_requests:
            self.request_counters[user_id].add()
            return RateLimitResult(
                allowed=True,
                current_count=current_count + 1,
                limit=rl_config.max_requests,
                remaining=remaining - 1,
                reset_after_seconds=round(rl_config.window_seconds, 1),
                retry_after_seconds=0,
                tier=tier,
                burst_used=False,
                in_cooldown=False,
            )

        # Within burst allowance → allow with flag
        if burst_count < rl_config.burst_allowance:
            self.request_counters[user_id].add()
            self.burst_counters[user_id].add()
            self.stats["total_burst_used"] += 1
            return RateLimitResult(
                allowed=True,
                current_count=current_count + 1,
                limit=rl_config.max_requests,
                remaining=0,
                reset_after_seconds=round(rl_config.window_seconds, 1),
                retry_after_seconds=0,
                tier=tier,
                burst_used=True,
                in_cooldown=False,
                flags=["burst_allowance_used"],
            )

        # Over limit — start cooldown if configured
        if rl_config.cooldown_seconds > 0:
            with self.lock:
                self.cooldown_until[user_id] = now + rl_config.cooldown_seconds
            self.stats["total_cooldown_triggered"] += 1
            return RateLimitResult(
                allowed=False,
                current_count=rl_config.max_requests + rl_config.burst_allowance,
                limit=rl_config.max_requests,
                remaining=0,
                reset_after_seconds=round(rl_config.cooldown_seconds, 1),
                retry_after_seconds=round(rl_config.cooldown_seconds, 1),
                tier=tier,
                burst_used=False,
                in_cooldown=True,
                flags=["rate_limit_exceeded", "cooldown_started"],
            )

        # No cooldown configured, just reject
        self.stats["total_blocked"] += 1
        reset_after = rl_config.window_seconds - self.request_counters[user_id].oldest_request_age()
        return RateLimitResult(
            allowed=False,
            current_count=current_count,
            limit=rl_config.max_requests,
            remaining=0,
            reset_after_seconds=round(max(0.1, reset_after), 1),
            retry_after_seconds=round(max(0.1, reset_after), 1),
            tier=tier,
            burst_used=False,
            in_cooldown=False,
            flags=["rate_limit_exceeded"],
        )

    def cleanup_expired(self, threshold_seconds: float = 300):
        """Remove stale user entries not seen in threshold_seconds."""
        now = time.monotonic()
        with self.lock:
            stale_users = []
            for user_id, counter in self.request_counters.items():
                if counter.count() == 0 and user_id not in self.cooldown_until:
                    stale_users.append(user_id)
                elif counter.count() == 0 and self.cooldown_until.get(user_id, 0) + threshold_seconds < now:
                    stale_users.append(user_id)

            for user_id in stale_users:
                self.request_counters.pop(user_id, None)
                self.burst_counters.pop(user_id, None)
                self.cooldown_until.pop(user_id, None)

            return len(stale_users)

    def get_user_status(self, user_id: str) -> Dict:
        """Get current rate limit status for a user."""
        tier = self.get_tier(user_id)
        tier_config = TIER_CONFIGS.get(tier, TIER_CONFIGS["free"])
        rl_config = tier_config["requests"]

        counter = self.request_counters.get(user_id)
        burst_counter = self.burst_counters.get(user_id)
        current = counter.count() if counter else 0
        burst = burst_counter.count() if burst_counter else 0
        cooldown = self.cooldown_until.get(user_id, 0)
        in_cooldown = cooldown > time.monotonic()

        return {
            "user_id": user_id,
            "tier": tier,
            "current_requests": current,
            "limit": rl_config.max_requests,
            "remaining": max(0, rl_config.max_requests - current),
            "burst_used": burst,
            "burst_limit": rl_config.burst_allowance,
            "in_cooldown": in_cooldown,
            "cooldown_remaining": round(max(0, cooldown - time.monotonic()), 1) if in_cooldown else 0,
        }

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            "tracked_users": len(self.request_counters),
            "active_users": sum(1 for c in self.request_counters.values() if c.count() > 0),
            "users_in_cooldown": sum(
                1 for u, t in self.cooldown_until.items() if t > time.monotonic()
            ),
        }

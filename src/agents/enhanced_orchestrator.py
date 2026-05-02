"""
Enhanced Orchestrator v3.0 — Security + Performance Layer
==========================================================
Wraps the original Orchestrator with:
  • Advanced OWASP security with rate limiting integration
  • Response caching for repeated queries
  • Memory-aware session management
  • Async pipeline support
  • Concurrent session handling improvements

The original Orchestrator is untouched for backward compatibility.
"""

import time, uuid, logging, threading
from typing import Optional

from src.config.settings import Settings
from src.app.timeutils import utc_now_iso

logger = logging.getLogger("supportoid.enhanced_orchestrator")


class EnhancedOrchestrator:
    """Orchestrator v3.0 with security, caching, rate limiting, and memory optimization."""

    BLOCKING_FLAGS = {
        "dangerous_operation",
        "injection_detected",
        "sql_injection_detected",
        "nosql_injection_detected",
        "command_injection_detected",
        "xss_detected",
        "ssrf_detected",
        "path_traversal_detected",
        "excessive_length",
    }

    def __init__(self, settings: Settings, store=None):
        # Import the original orchestrator
        from src.orchestrator import Orchestrator
        from src.agents.security_layer import SecurityLayer
        from src.agents.rate_limiter import UserRateLimiter
        from src.agents.response_cache import ResponseCache
        from src.agents.memory_optimizer import MemoryOptimizer

        # Wrap the original
        self.original = Orchestrator(settings, store=store)
        self.original.initialize()

        # New components
        self.security = SecurityLayer()
        self.rate_limiter = UserRateLimiter()
        self.response_cache = ResponseCache(classifier=self.original.classifier)
        self.memory_optimizer = MemoryOptimizer()

        # Concurrent session handling
        self._session_locks: dict = {}
        self._global_lock = threading.Lock()
        self._max_session_messages = 100  # Prevent runaway session growth
        self._session_cleanup_interval = 3600  # 1 hour
        self._last_cleanup = time.monotonic()

        # Thread safety for stats
        self._stats_lock = threading.Lock()
        self.enhanced_stats = {
            "security_blocks": 0,
            "rate_limit_blocks": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "sessions_cleaned": 0,
            "concurrent_processes": 0,
            "max_concurrent": 0,
            "errors": 0,
        }

        # OWASP advanced patterns (loaded once)
        self._owasp_patterns_loaded = True

        logger.info("EnhancedOrchestrator v3.0 initialized with security, caching, rate limiting")

    # ── Process with full security + caching ──

    def process(self, message: str, conversation_id: str = None,
                user_id: str = "anonymous", tier: str = "free") -> dict:
        """Run full pipeline with security, rate limiting, and caching."""
        concurrent_start = self._track_concurrent()
        try:
            return self._process_with_security(message, conversation_id, user_id, tier)
        except Exception as e:
            with self._stats_lock:
                self.enhanced_stats["errors"] += 1
            logger.error(f"Processing error for user {user_id}: {e}")
            return {
                "conversation_id": conversation_id or f"conv_error_{uuid.uuid4().hex[:8]}",
                "response": "I'm sorry, something went wrong while processing your request. Please try again.",
                "error": str(e),
                "processing_time_ms": 0,
            }
        finally:
            self._untrack_concurrent(concurrent_start)

    def _process_with_security(self, message: str, conversation_id: str,
                                user_id: str, tier: str) -> dict:
        start = time.monotonic()

        # 1. Security check (OWASP guardrails)
        sec_result = self.security.check_input(message, user_id)
        should_block = (
            not sec_result.passed
            and (
                bool(self.BLOCKING_FLAGS.intersection(sec_result.flags))
                or sec_result.threat_level in {"high", "critical"}
            )
        )
        if should_block:
            with self._stats_lock:
                self.enhanced_stats["security_blocks"] += 1
            return {
                "conversation_id": conversation_id or f"conv_blocked_{uuid.uuid4().hex[:8]}",
                "response": "I cannot process that request as written. Please remove unsafe instructions, embedded code, or sensitive tokens and try again.",
                "blocked": True,
                "source": "guardrail:input",
                "processing_time_ms": round((time.monotonic() - start) * 1000, 1),
            }

        # 2. Rate limit check (configurable per-user)
        rl_result = self.rate_limiter.check(user_id, tier)
        if not rl_result.allowed:
            with self._stats_lock:
                self.enhanced_stats["rate_limit_blocks"] += 1
            return {
                "response": f"You've reached the rate limit for your plan ({rl_result.tier}). Please wait {rl_result.retry_after_seconds}s before trying again.",
                "rate_limit": {
                    "tier": rl_result.tier,
                    "remaining": rl_result.remaining,
                    "retry_after_seconds": rl_result.retry_after_seconds,
                    "burst_used": rl_result.burst_used,
                },
                "rate_limited": True,
                "processing_time_ms": round((time.monotonic() - start) * 1000, 1),
            }

        # Use sanitized input if secrets were detected
        effective_message = sec_result.sanitized_input

        # 3. Try response cache (classify first to get intent for cache key)
        classification = self.original.classifier.classify(effective_message)
        intent = classification.get("intent", "")
        cache_result = self.response_cache.get(effective_message, intent)
        if cache_result.hit:
            with self._stats_lock:
                self.enhanced_stats["cache_hits"] += 1
            return {
                "conversation_id": conversation_id or f"conv_cache_{uuid.uuid4().hex[:8]}",
                "response": cache_result.response_text,
                "source": f"cache:{cache_result.source}",
                "cached_at_seconds_ago": cache_result.cached_at_seconds_ago,
                "from_cache": True,
                "processing_time_ms": round((time.monotonic() - start) * 1000, 1),
            }

        with self._stats_lock:
            self.enhanced_stats["cache_misses"] += 1

        # 4. Session management with concurrent safety
        conversation_id = conversation_id or f"conv_{uuid.uuid4().hex[:8]}"
        session = self._get_session(conversation_id, user_id)

        # Session message limit
        if len(session["messages"]) > self._max_session_messages:
            session["messages"] = session["messages"][-50:]

        # Thread-safe session processing
        session_lock = self._get_session_lock(conversation_id)
        with session_lock:
            result = self.original.process(effective_message, conversation_id, user_id)

        output_check = self.security.check_output(str(result.get("response") or ""))
        if not output_check.passed:
            with self._stats_lock:
                self.enhanced_stats["security_blocks"] += 1
            return {
                "conversation_id": result.get("conversation_id", conversation_id),
                "response": "I could not safely return a response for that request. Please rephrase it or provide a little more context.",
                "blocked": True,
                "source": "guardrail:output",
                "processing_time_ms": round((time.monotonic() - start) * 1000, 1),
            }

        # 5. Cache the response
        self.response_cache.put(
            message=effective_message,
            response_text=result["response"],
            intent=result.get("intent", ""),
            source=result.get("source", ""),
            quality_score=result.get("quality_score", 0),
        )

        # 6. Add security + rate limit info
        result["security"] = {
            "checks_passed": sec_result.checks_passed,
            "checks_failed": sec_result.checks_failed,
            "flags": sec_result.flags,
        }
        if rl_result.burst_used:
            result["burst_used"] = True
            result["burst_remaining"] = self.rate_limiter.get_user_status(user_id).get("burst_limit", 0)

        # 7. Memory maintenance
        self._periodic_maintenance()

        return result

    # ── Security operations ──

    def get_security_report(self, last_n: int = 100) -> dict:
        """Get OWASP security audit report."""
        return {
            **self.security.get_audit_report(last_n),
            "threat_summary": self.security.get_threat_summary(last_n=min(last_n, 50)),
            "security_blocks_total": self._stats_lock_read("security_blocks"),
            "rate_limit_blocks_total": self._stats_lock_read("rate_limit_blocks"),
        }

    def get_rate_limit_status(self, user_id: str = "anonymous") -> dict:
        """Get rate limit status for a user."""
        return self.rate_limiter.get_user_status(user_id)

    # ── Cache operations ──

    def get_cache_stats(self) -> dict:
        """Get cache hit/miss statistics."""
        return {
            **self.response_cache.get_stats(),
            "total_hits": self._stats_lock_read("cache_hits"),
            "total_misses": self._stats_lock_read("cache_misses"),
        }

    def clear_cache(self) -> int:
        """Clear all cached responses."""
        return self.response_cache.clear()

    # ── Memory operations ──

    def get_memory_status(self) -> dict:
        """Get current memory optimization status."""
        status = self.memory_optimizer.get_memory_status(
            cache_entry_count=len(self.response_cache._cache),
            session_count=len(self.original.sessions),
        )
        return {
            "total_mb": status.total_mb,
            "used_mb": status.used_mb,
            "process_rss_mb": status.process_rss_mb,
            "status": status.status,
            "pressure": status.pressure,
            "recommendations": status.recommendations,
        }

    def force_cleanup(self) -> dict:
        """Force memory cleanup."""
        return self.memory_optimizer.force_cleanup()

    # ── Session management ──

    def prune_stale_sessions(self, max_age_seconds: float = 3600, age_factor: float = 1.0) -> int:
        """Remove stale sessions to free memory."""
        cutoff = time.monotonic() - (max_age_seconds * age_factor)
        pruned = 0
        to_remove = []

        with self._global_lock:
            for cid, session in self.original.sessions.items():
                if "_created_mono" not in session:
                    continue
                try:
                    created = float(session["_created_mono"])
                except (TypeError, ValueError):
                    continue
                if created < cutoff:
                    to_remove.append(cid)
            for cid in to_remove:
                del self.original.sessions[cid]
                pruned += 1

        with self._stats_lock:
            self.enhanced_stats["sessions_cleaned"] += pruned

        return pruned

    def get_active_sessions(self) -> dict:
        """Get active session info without full data."""
        sessions = {}
        for cid, session in self.original.sessions.items():
            sessions[cid] = {
                "user_id": session.get("user_id", "unknown"),
                "message_count": len(session.get("messages", [])),
                "created_at": session.get("created_at", ""),
            }
        return sessions

    def get_session_lock_info(self) -> dict:
        """Get info about session lock contention."""
        return {
            "total_session_locks": len(self._session_locks),
            "concurrent_processes_now": self._stats_lock_read("concurrent_processes"),
            "max_concurrent_ever": self._stats_lock_read("max_concurrent"),
        }

    # ── Tier management ──

    def set_user_tier(self, user_id: str, tier: str):
        """Set the rate limit tier for a user."""
        self.rate_limiter.set_user_tier(user_id, tier)

    # ── Internal helpers ──

    def _get_session(self, conversation_id: str, user_id: str) -> dict:
        """Get or create session with concurrent safety."""
        if conversation_id not in self.original.sessions:
            with self._global_lock:
                if conversation_id not in self.original.sessions:
                    mono = time.monotonic()
                    self.original.sessions[conversation_id] = {
                        "conversation_id": conversation_id,
                        "history": [],
                        "messages": [],
                        "user_id": user_id,
                        "created_at": utc_now_iso(),
                        "_created_mono": mono,
                    }
        return self.original.sessions[conversation_id]

    def _get_session_lock(self, conversation_id: str) -> threading.Lock:
        """Get or create a per-session lock for thread safety."""
        if conversation_id not in self._session_locks:
            with self._global_lock:
                if conversation_id not in self._session_locks:
                    self._session_locks[conversation_id] = threading.Lock()
        return self._session_locks[conversation_id]

    def _track_concurrent(self) -> float:
        """Track concurrent processing."""
        with self._stats_lock:
            self.enhanced_stats["concurrent_processes"] += 1
            current = self.enhanced_stats["concurrent_processes"]
            if current > self.enhanced_stats["max_concurrent"]:
                self.enhanced_stats["max_concurrent"] = current
        return time.monotonic()

    def _untrack_concurrent(self, start: float):
        """Untrack concurrent processing."""
        with self._stats_lock:
            self.enhanced_stats["concurrent_processes"] = max(
                0, self.enhanced_stats["concurrent_processes"] - 1
            )

    def _stats_lock_read(self, key: str):
        """Thread-safe stats read."""
        with self._stats_lock:
            return self.enhanced_stats.get(key, 0)

    def _periodic_maintenance(self):
        """Run periodic maintenance (cleanup, GC, etc.)."""
        with self._global_lock:
            now = time.monotonic()
            if now - self._last_cleanup < self._session_cleanup_interval:
                return
            self._last_cleanup = now

        # Run maintenance in a non-blocking way
        def _maintenance():
            self.response_cache.cleanup_expired()
            self.rate_limiter.cleanup_expired()
            self.memory_optimizer.periodic_maintenance(
                cache_cleanup_fn=self.response_cache.cleanup_expired,
                session_prune_fn=self.prune_stale_sessions,
            )

        threading.Thread(target=_maintenance, daemon=True).start()

    # ── Full stats ──

    def get_stats(self) -> dict:
        original_stats = self.original.get_stats()
        cache_stats = self.response_cache.get_stats()

        combined_hit_rate = 0
        total_lookups = self._stats_lock_read("cache_hits") + self._stats_lock_read("cache_misses")
        if total_lookups > 0:
            combined_hit_rate = round(self._stats_lock_read("cache_hits") / total_lookups * 100, 1)

        return {
            **original_stats,
            # Security stats
            "security_blocks_total": self._stats_lock_read("security_blocks"),
            "rate_limit_blocks_total": self._stats_lock_read("rate_limit_blocks"),
            # Cache stats
            "total_cache_hits": self._stats_lock_read("cache_hits"),
            "total_cache_misses": self._stats_lock_read("cache_misses"),
            "cache_hit_rate": combined_hit_rate,
            "cache_entries": cache_stats.get("current_entries", 0),
            # Concurrency stats
            "concurrent_processes": self._stats_lock_read("concurrent_processes"),
            "max_concurrent_ever": self._stats_lock_read("max_concurrent"),
            "sessions_cleaned": self._stats_lock_read("sessions_cleaned"),
            # Memory info
            "memory_rss_mb": round(self.memory_optimizer._get_process_rss(), 1),
            "errors": self._stats_lock_read("errors"),
            # Version
            "version": "3.0-enhanced",
        }

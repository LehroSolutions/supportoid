"""
Memory Optimizer — Runtime Memory Usage Optimization
=====================================================
Proactive memory management for long-running SupportOID instances.

Features:
  • Memory usage monitoring with thresholds
  • Automatic cache cleanup on memory pressure
  • Session pruning for stale conversations
  • Orphaned data detection and cleanup
  • Periodic garbage collection scheduling
"""

import os, gc, sys, time, logging, threading
from typing import Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("supportoid.memory")


@dataclass
class MemoryStatus:
    total_mb: float
    used_mb: float
    available_mb: float
    process_rss_mb: float
    swap_total_mb: float
    swap_used_mb: float
    cache_entries: int
    session_count: int
    status: str  # "healthy", "warning", "critical"
    pressure: float  # 0.0 - 1.0
    recommendations: list = field(default_factory=list)


class MemoryOptimizer:
    """Proactive memory optimization for SupportOID."""

    def __init__(self,
                 warning_threshold: float = 0.7,   # 70% triggers warning
                 critical_threshold: float = 0.9,   # 90% triggers aggressive cleanup
                 gc_interval_seconds: float = 300,   # Run GC every 5 minutes
                 auto_cleanup: bool = True):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.gc_interval_seconds = gc_interval_seconds
        self.auto_cleanup = auto_cleanup
        self._last_gc = time.monotonic()
        self._last_cleanup = time.monotonic()
        self.lock = threading.Lock()

        # Historical tracking
        self.memory_history: list = []
        self.max_history = 60  # Keep 60 snapshots

        # Stats
        self.stats = {
            "gc_runs": 0,
            "cleanups_triggered": 0,
            "sessions_pruned": 0,
            "cache_entries_freed": 0,
            "total_freed_mb": 0.0,
            "peak_process_mb": 0.0,
            "warnings": 0,
            "critical_alerts": 0,
        }

    def get_memory_status(self,
                          cache_entry_count: int = 0,
                          session_count: int = 0) -> MemoryStatus:
        """Get current memory status with recommendations."""
        mem_info = self._read_proc_meminfo()
        process_rss = self._get_process_rss()

        total_mb = mem_info.get("MemTotal", 0) / 1024
        available_mb = mem_info.get("MemAvailable", mem_info.get("MemFree", 0)) / 1024
        used_mb = total_mb - available_mb
        swap_total_mb = mem_info.get("SwapTotal", 0) / 1024
        swap_used_mb = (mem_info.get("SwapTotal", 0) - mem_info.get("SwapFree", 0)) / 1024

        # Process memory (if total is known)
        if total_mb > 0:
            pressure = process_rss / total_mb
        else:
            # Fallback: estimate based on available
            pressure = min(1.0, process_rss / max(available_mb, 1))

        # Track peak
        if process_rss > self.stats["peak_process_mb"]:
            self.stats["peak_process_mb"] = process_rss

        status = "healthy"
        recommendations = []

        if pressure >= self.critical_threshold:
            status = "critical"
            recommendations = self._get_recommendations(process_rss, cache_entry_count, session_count, pressure)
            self.stats["critical_alerts"] += 1
        elif pressure >= self.warning_threshold:
            status = "warning"
            recommendations = self._get_recommendations(process_rss, cache_entry_count, session_count, pressure)
            self.stats["warnings"] += 1

        # Record history
        self.memory_history.append({
            "time": time.monotonic(),
            "process_rss_mb": round(process_rss, 1),
            "pressure": round(pressure, 3),
            "status": status,
        })
        if len(self.memory_history) > self.max_history:
            self.memory_history = self.memory_history[-self.max_history:]

        return MemoryStatus(
            total_mb=round(total_mb, 1) if total_mb else 0,
            used_mb=round(used_mb, 1),
            available_mb=round(available_mb, 1),
            process_rss_mb=round(process_rss, 1),
            swap_total_mb=round(swap_total_mb, 1),
            swap_used_mb=round(swap_used_mb, 1),
            cache_entries=cache_entry_count,
            session_count=session_count,
            status=status,
            pressure=round(pressure, 3),
            recommendations=recommendations,
        )

    def periodic_maintenance(self,
                            cache_cleanup_fn=None,
                            session_prune_fn=None,
                            orphan_cleanup_fn=None) -> Dict:
        """Run periodic maintenance if conditions are met."""
        with self.lock:
            now = time.monotonic()
            actions_taken = {"gc": False, "cache_cleaned": False, "sessions_pruned": 0, "orphans_cleaned": False}

            # Run GC if interval elapsed
            if now - self._last_gc >= self.gc_interval_seconds:
                self._run_gc()
                actions_taken["gc"] = True
                self._last_gc = now

            # Check if cleanup needed
            if self.auto_cleanup and (now - self._last_cleanup >= 60):
                mem_status = self.get_memory_status()

                if mem_status.status in ("warning", "critical"):
                    self.stats["cleanups_triggered"] += 1

                    # Cache cleanup
                    if cache_cleanup_fn:
                        freed = cache_cleanup_fn()
                        actions_taken["cache_cleaned"] = True
                        self.stats["cache_entries_freed"] += freed

                    # Session pruning (aggressive if critical)
                    if session_prune_fn:
                        max_age = 600 if mem_status.status == "critical" else 1800
                        pruned = session_prune_fn(max_age_seconds=max_age, age_factor=1.5)
                        actions_taken["sessions_pruned"] += pruned
                        self.stats["sessions_pruned"] += pruned

                    # Orphan cleanup
                    if orphan_cleanup_fn:
                        orphan_cleanup_fn()
                        actions_taken["orphans_cleaned"] = True

                    self._last_cleanup = now

            return actions_taken

    def _run_gc(self):
        """Trigger garbage collection."""
        before = self._get_process_rss()
        collected = gc.collect()
        after = self._get_process_rss()
        self.stats["gc_runs"] += 1
        freed = max(0, before - after)
        self.stats["total_freed_mb"] += freed
        logger.debug(f"GC: collected {collected} objects, freed ~{freed:.1f} MB")

    def force_cleanup(self) -> Dict:
        """Force immediate cleanup. Returns actions taken."""
        before_rss = self._get_process_rss()
        gc.collect()
        after_rss = self._get_process_rss()
        freed = max(0, before_rss - after_rss)
        self.stats["gc_runs"] += 1
        self.stats["total_freed_mb"] += freed
        return {
            "gc_triggered": True,
            "rss_freed_mb": round(freed, 1),
            "process_rss_after_mb": round(after_rss, 1),
        }

    def get_diagnostics(self) -> Dict:
        """Get diagnostic info for memory troubleshooting."""
        return {
            "memory_status": {
                "total_allocated_mb": self._get_process_rss(),
                "gc_enabled": gc.isenabled(),
                "gc_threshold": gc.get_threshold(),
                "gc_stats": gc.get_stats(),
            },
            "optimizer_stats": self.stats,
            "memory_trend": self._get_trend(),
        }

    def _get_recommendations(self, process_rss: float, cache_entries: int,
                            session_count: int, pressure: float) -> list:
        """Generate optimization recommendations."""
        recs = []
        if process_rss > 1024:
            recs.append("Process using >1GB RAM — reduce cache size or session retention")
        if cache_entries > 1000:
            recs.append(f"Cache has {cache_entries} entries — consider reducing max_entries")
        if session_count > 500:
            recs.append(f"{session_count} active sessions — consider pruning inactive sessions")
        if pressure > 0.8:
            recs.append(f"Memory pressure at {pressure*100:.0f}% — reduce cache or increase container memory")
        if self.stats["gc_runs"] == 0:
            recs.append("Garbage collection hasn't run — enable periodic maintenance")
        return recs

    def _get_trend(self) -> str:
        """Analyze memory trend."""
        if len(self.memory_history) < 5:
            return "insufficient_data"
        recent = [h["process_rss_mb"] for h in self.memory_history[-5:]]
        if recent[-1] > recent[0] * 1.1:
            return "increasing"
        elif recent[-1] < recent[0] * 0.9:
            return "decreasing"
        return "stable"

    @staticmethod
    def _read_proc_meminfo() -> Dict[str, int]:
        """Read /proc/meminfo values."""
        info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        value = int(parts[1])  # in kB
                        info[key] = value
        except (FileNotFoundError, PermissionError):
            pass
        return info

    @staticmethod
    def _get_process_rss() -> float:
        """Get current process RSS in MB."""
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024  # kB → MB
        except (FileNotFoundError, PermissionError):
            pass
        # Fallback: use os.getpid() and psutil-like approach
        try:
            pid = os.getpid()
            for line in open(f"/proc/{pid}/status"):
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
        except (FileNotFoundError, PermissionError):
            pass
        return 0.0

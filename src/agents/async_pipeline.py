"""
Async Processing Pipeline — Non-Blocking Request Processing
============================================================
Asynchronous pipeline for SupportOID request processing.

Features:
  • asyncio-based async processing pipeline
  • Background task queue for heavy operations
  • Priority-based task scheduling
  • Configurable worker pool size
  • Result callbacks and progress tracking
  • Graceful shutdown with task drain
"""

import asyncio, time, uuid, logging, threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Callable, Any, List
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("supportoid.async_pipeline")


class TaskPriority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PipelineTask:
    task_id: str
    priority: TaskPriority
    status: TaskStatus
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    result: Optional[Any] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return round((self.completed_at - self.started_at) * 1000, 1)
        return None

    @property
    def processing_time_ms(self) -> Optional[float]:
        if self.started_at:
            end = self.completed_at or time.monotonic()
            return round((end - self.started_at) * 1000, 1)
        return None


class AsyncPipeline:
    """Async processing pipeline with worker pool and priority queue."""

    def __init__(self, worker_pool_size: int = 4, max_queue_size: int = 1000):
        self.worker_pool_size = worker_pool_size
        self.max_queue_size = max_queue_size
        self._executor = ThreadPoolExecutor(max_workers=worker_pool_size)
        self._queue: asyncio.PriorityQueue = None
        self._tasks: Dict[str, PipelineTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self._workers: List[asyncio.Task] = []
        self._callbacks: Dict[str, List[Callable]] = {}
        self._semaphore: asyncio.Semaphore = None

        # Stats
        self.stats = {
            "total_submitted": 0,
            "total_completed": 0,
            "total_failed": 0,
            "total_cancelled": 0,
            "total_retries": 0,
            "avg_processing_ms": 0.0,
        }

    async def start(self):
        """Start the pipeline workers."""
        if self._running:
            return
        self._running = True
        self._queue = asyncio.PriorityQueue(maxsize=self.max_queue_size)
        self._semaphore = asyncio.Semaphore(self.worker_pool_size)

        for i in range(self.worker_pool_size):
            worker = asyncio.create_task(self._worker_loop(i))
            self._workers.append(worker)

        logger.info(f"AsyncPipeline started with {self.worker_pool_size} workers")

    @staticmethod
    def _normalize_priority(priority: TaskPriority | int) -> TaskPriority:
        if isinstance(priority, TaskPriority):
            return priority
        try:
            return TaskPriority(int(priority))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid task priority: {priority}") from exc

    async def stop(self, drain: bool = True, timeout: float = 30):
        """Stop the pipeline, optionally draining remaining tasks."""
        self._running = False

        if drain:
            try:
                await asyncio.wait_for(self._queue.join(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Pipeline drain timeout after {timeout}s")

        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        # Shutdown executor
        self._executor.shutdown(wait=not drain)

        logger.info("AsyncPipeline stopped")

    async def submit(self, fn, *args, priority: TaskPriority = TaskPriority.NORMAL,
                     task_id: str = None, callback: Callable = None,
                     metadata: Dict = None, **kwargs) -> PipelineTask:
        """Submit a task to the pipeline for async execution."""
        task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        priority = self._normalize_priority(priority)

        task = PipelineTask(
            task_id=task_id,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=time.monotonic(),
            max_retries=3,
            metadata=metadata or {},
        )

        with self._lock:
            self._tasks[task_id] = task
            if callback:
                self._callbacks.setdefault(task_id, []).append(callback)

        self.stats["total_submitted"] += 1

        # Use priority value as sort key (lower = higher priority)
        await self._queue.put((task.priority.value, task.created_at, fn, args, kwargs, task_id))

        logger.debug(f"Task {task_id} submitted with priority {task.priority.name}")
        return task

    def submit_sync(self, fn, *args, priority: TaskPriority = TaskPriority.NORMAL,
                    task_id: str = None, callback: Callable = None,
                    metadata: Dict = None, **kwargs) -> PipelineTask:
        """Synchronous task submission (for non-async contexts)."""
        task_id = task_id or f"task_{uuid.uuid4().hex[:8]}"
        priority = self._normalize_priority(priority)
        task = PipelineTask(
            task_id=task_id,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=time.monotonic(),
            max_retries=3,
            metadata=metadata or {},
        )

        with self._lock:
            self._tasks[task_id] = task
            if callback:
                self._callbacks.setdefault(task_id, []).append(callback)

        self.stats["total_submitted"] += 1

        # Schedule via event loop if one exists
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._queue.put((task.priority.value, task.created_at, fn, args, kwargs, task_id))
            )
        except RuntimeError:
            # No running event loop - will be queued when pipeline starts
            pass

        return task

    def get_task(self, task_id: str) -> Optional[PipelineTask]:
        """Get task status by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def get_status(self, task_id: str) -> Optional[str]:
        """Get task status string."""
        task = self.get_task(task_id)
        return task.status.value if task else None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self.stats["total_cancelled"] += 1
                self._callbacks.pop(task_id, None)
                return True
            return False

    async def _worker_loop(self, worker_id: int):
        """Worker loop that processes tasks from the priority queue."""
        while self._running:
            try:
                priority_val, created_at, fn, args, kwargs, task_id = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            async with self._semaphore:
                await self._execute_task(fn, args, kwargs, task_id)
                self._queue.task_done()

    async def _execute_task(self, fn, args, kwargs, task_id: str):
        """Execute a single task with retry logic."""
        with self._lock:
            task = self._tasks.get(task_id)

        if not task or task.status == TaskStatus.CANCELLED:
            return

        task.status = TaskStatus.RUNNING
        task.started_at = time.monotonic()

        try:
            loop = asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = await loop.run_in_executor(self._executor, fn, *args)

            task.status = TaskStatus.COMPLETED
            task.completed_at = time.monotonic()
            task.result = result

            with self._lock:
                self.stats["total_completed"] += 1
                elapsed = task.elapsed_ms or 0
                total = self.stats["total_completed"]
                self.stats["avg_processing_ms"] = round(
                    (self.stats["avg_processing_ms"] * (total - 1) + elapsed) / total, 1
                )

                # Notify callbacks
                for cb in self._callbacks.get(task_id, []):
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(task)
                        else:
                            cb(task)
                    except Exception as e:
                        logger.warning(f"Callback error for task {task_id}: {e}")

        except Exception as e:
            task.retry_count += 1
            if task.retry_count <= task.max_retries:
                with self._lock:
                    self.stats["total_retries"] += 1
                logger.debug(f"Task {task_id} retry {task.retry_count}/{task.max_retries}: {e}")
                # Re-queue with higher priority
                await self._queue.put((task.priority.value - 0.1, time.monotonic(), fn, args, kwargs, task_id))
            else:
                task.status = TaskStatus.FAILED
                task.completed_at = time.monotonic()
                task.error = str(e)
                with self._lock:
                    self.stats["total_failed"] += 1
                logger.error(f"Task {task_id} failed after {task.max_retries} retries: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        with self._lock:
            tasks_by_status = {}
            for task in self._tasks.values():
                status = task.status.value
                tasks_by_status[status] = tasks_by_status.get(status, 0) + 1

            return {
                **self.stats,
                "worker_pool_size": self.worker_pool_size,
                "total_tracked": len(self._tasks),
                "tasks_by_status": tasks_by_status,
                "queue_size": self._queue.qsize() if self._queue else 0,
                "queue_full": self._queue.full() if self._queue else False,
                "running": self._running,
            }


async def process_request_async(pipeline: AsyncPipeline, processor_fn, message: str,
                                conversation_id: str = None, user_id: str = "anonymous",
                                priority: TaskPriority = TaskPriority.NORMAL) -> str:
    """
    Convenience function to submit a support request for async processing.
    Returns task_id for status tracking.
    """
    task = await pipeline.submit(
        processor_fn, message, conversation_id, user_id,
        priority=priority,
        metadata={
            "message_preview": message[:100],
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
    )
    return task.task_id


def create_enhanced_orchestrator_wrapper(orchestrator, rate_limiter, response_cache,
                                          memory_optimizer):
    """
    Create a wrapped process function that adds caching + rate limiting
    for use with the async pipeline.
    """
    def wrapped_process(message: str, conversation_id: str = None,
                       user_id: str = "anonymous"):
        # 1. Rate limit check
        rl_result = rate_limiter.check(user_id)
        if not rl_result.allowed:
            return {
                "error": "rate_limit_exceeded",
                "retry_after_seconds": rl_result.retry_after_seconds,
                "tier": rl_result.tier,
                "remaining": rl_result.remaining,
            }

        # 2. Try cache first
        intent = ""  # Cache lookup needs intent — use empty for exact match
        cache_result = response_cache.get(message, intent)
        if cache_result.hit:
            return {
                "response": cache_result.response_text,
                "source": f"cache:{cache_result.source}",
                "cached_at_seconds_ago": cache_result.cached_at_seconds_ago,
                "cache_key": cache_result.cache_key,
                "processing_time_ms": 1,
                "from_cache": True,
            }

        # 3. Process normally through orchestrator
        result = orchestrator.process(message, conversation_id, user_id)

        # 4. Cache the result if it's a normal response
        if result.get("response"):
            response_cache.put(
                message=message,
                response_text=result["response"],
                intent=result.get("intent", ""),
                source=result.get("source", ""),
                quality_score=result.get("quality_score", 0),
            )

        # 5. Add rate limit info to response
        if rl_result.burst_used:
            result["burst_used"] = True

        result["from_cache"] = False
        return result

    return wrapped_process

"""Background scheduling primitives for Autonomous Agent v2.1.

This module will orchestrate batched processing while respecting resource
limits. The current implementation offers a minimal interface to schedule tasks
without altering existing VAMP behaviour.
"""
from __future__ import annotations

import threading
from queue import Queue, Empty
from typing import Callable, Optional


class BackgroundScheduler:
    """Simple worker that processes callables in the background."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self.queue: Queue[Callable[[], None]] = Queue(maxsize=max_queue_size)
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background worker thread if not already running."""

        if self.thread and self.thread.is_alive():
            return

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        """Signal the worker thread to exit gracefully."""

        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=1.0)

    def schedule(self, task: Callable[[], None]) -> bool:
        """Attempt to enqueue a task for background execution.

        Returns ``True`` on success and ``False`` if the queue is full. This
        approach avoids blocking the caller while keeping behaviour predictable.
        """

        if self._stop_event.is_set():
            return False

        try:
            self.queue.put(task, block=False)
            return True
        except Exception:
            return False

    def _worker(self) -> None:
        """Continuously process tasks until stopped."""

        while not self._stop_event.is_set():
            try:
                task = self.queue.get(timeout=0.1)
            except Empty:
                continue

            try:
                task()
            finally:
                self.queue.task_done()

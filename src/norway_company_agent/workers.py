from __future__ import annotations

import multiprocessing
import time
from multiprocessing.connection import wait


def _worker(connection, function, shared):
    try:
        while True:
            task = connection.recv()
            try:
                result = (True, function(task, shared))
            except Exception as exc:
                result = (False, f"{type(exc).__name__}: {exc}"[:500])
            connection.send(result)
    except (EOFError, BrokenPipeError):
        pass
    finally:
        connection.close()


class BoundedWorkers:
    """Reusable isolated workers; timed-out work cannot mutate parent state.

    Pipes avoid queue feeder threads and their shutdown joins. Each worker has
    at most one task. A stuck task is killed and the slot is recreated lazily.
    """

    def __init__(self, function, shared, workers: int, context=None):
        self.context = context or multiprocessing.get_context("spawn")
        self.function = function
        self.shared = shared
        self.slots = [None] * max(1, workers)

    def submit(self, task, timeout: float) -> int:
        for index, slot in enumerate(self.slots):
            if slot is not None and slot["task"] is not None:
                continue
            if slot is None:
                parent, child = self.context.Pipe()
                process = self.context.Process(target=_worker, args=(child, self.function, self.shared), daemon=True)
                process.start()
                child.close()
                slot = self.slots[index] = {"process": process, "pipe": parent, "task": None}
            slot["task"] = task
            slot["expires"] = time.monotonic() + timeout
            slot["pipe"].send(task)
            return index
        raise RuntimeError("No idle worker")

    @property
    def active(self) -> int:
        return sum(slot is not None and slot["task"] is not None for slot in self.slots)

    def poll(self, timeout: float = 0.1):
        active = [slot for slot in self.slots if slot and slot["task"] is not None]
        if not active:
            return []
        delay = max(0.0, min(timeout, min(slot["expires"] for slot in active) - time.monotonic()))
        ready = wait([slot["pipe"] for slot in active], timeout=delay)
        results = []
        for index, slot in enumerate(self.slots):
            if not slot or slot["task"] is None:
                continue
            task = slot["task"]
            if slot["pipe"] in ready:
                try:
                    ok, value = slot["pipe"].recv()
                    results.append((task, ok, value))
                    slot["task"] = None
                    continue
                except (EOFError, OSError):
                    reason = "worker_exit"
            elif time.monotonic() >= slot["expires"]:
                reason = "company_timeout"
            elif not slot["process"].is_alive():
                reason = "worker_exit"
            else:
                continue
            results.append((task, False, reason))
            self._stop(index)
        return results

    def _stop(self, index):
        slot = self.slots[index]
        if slot is None:
            return
        process = slot["process"]
        if process.is_alive():
            process.kill()
        process.join(timeout=0.5)
        slot["pipe"].close()
        process.close()
        self.slots[index] = None

    def close(self):
        incomplete = [slot["task"] for slot in self.slots if slot and slot["task"] is not None]
        for index in range(len(self.slots)):
            self._stop(index)
        return incomplete

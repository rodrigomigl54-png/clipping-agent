"""Continuous local operation: periodic research + processing cycles.

Runs only while this computer is on and the process is running. Supports pause/resume (via the
database flag, so another terminal can toggle it), graceful shutdown on SIGINT/SIGTERM, a
single-runner lock, a heartbeat, and crash recovery at start-up.
"""
from __future__ import annotations

import os
import signal
import time
import traceback
from pathlib import Path

from ..core.database import now_iso
from ..core.logger import get_logger
from .orchestrator import Orchestrator

log = get_logger("scheduler")


class RunnerLock:
    def __init__(self, path: Path):
        self.path = path

    def _alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            return False
        except PermissionError:
            return True

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text().strip() or 0)
            except ValueError:
                pid = 0
            if pid and pid != os.getpid() and self._alive(pid):
                return False
        self.path.write_text(str(os.getpid()))
        return True

    def release(self) -> None:
        try:
            if self.path.exists() and self.path.read_text().strip() == str(os.getpid()):
                self.path.unlink()
        except OSError:
            pass

    def holder(self) -> int | None:
        try:
            pid = int(self.path.read_text().strip())
            return pid if self._alive(pid) else None
        except (OSError, ValueError):
            return None


class Scheduler:
    def __init__(self, orch: Orchestrator, interval_minutes: float | None = None, profiles: list[str] | None = None):
        self.orch = orch
        self.interval = 60 * (interval_minutes or orch.settings.global_.research.interval_minutes)
        self.profiles = profiles
        self._stop = False
        self.lock = RunnerLock(orch.settings.work_dir / ".runner.lock")
        orch.should_stop = lambda: self._stop

    def _handle(self, signum, _frame):
        log.warning("signal %s received: finishing current step then shutting down", signum)
        self._stop = True

    def run(self, max_cycles: int | None = None) -> int:
        if not self.lock.acquire():
            print(f"Another runner is active (pid {self.lock.holder()}). Use `status` to inspect it.")
            return 1
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)
        db = self.orch.db
        try:
            rec = self.orch.recover()
            print(f"Recovery: {rec}")
            db.set_state("runner_pid", str(os.getpid()))
            db.set_state("runner_started", now_iso())
            cycles = 0
            while not self._stop:
                db.set_state("heartbeat", now_iso())
                if db.get_state("paused") == "1":
                    db.set_state("activity", "paused")
                    self._sleep(15)
                    continue
                try:
                    started = time.time()
                    res = self.orch.run_cycle(self.profiles)
                    clips = sum(len(v["processing"]["clips"]) for v in res.values())
                    print(f"[{now_iso()}] cycle complete: {clips} clip attempts in {time.time() - started:.0f}s")
                except Exception as e:  # never let one cycle kill the runner
                    db.log_error("scheduler.cycle", None, str(e), traceback.format_exc())
                    log.error("cycle failed: %s", e)
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    break
                db.set_state("activity", "waiting")
                db.set_state("next_cycle_at", time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + self.interval)))
                self._sleep(self.interval)
        finally:
            db.set_state("activity", "stopped")
            db.set_state("runner_pid", "")
            self.lock.release()
            print("Clipping machine stopped cleanly.")
        return 0

    def _sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while not self._stop and time.time() < end:
            time.sleep(min(2.0, end - time.time()))
            if self.orch.db.get_state("run_now") == "1":
                self.orch.db.set_state("run_now", "0")
                return

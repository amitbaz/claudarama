"""Supervisor: picks queued turns, builds briefs, spawns claude -p, captures output.

The server of the CEO's Session runs one (``run``) for as long as the Session is open (ADR-0003).

Health: a crash (non-zero exit) is retried once on the same model. A stalled turn
(no stdout for ``stall_timeout`` seconds) is killed; it fails unless ``org.yaml``
opts in to escalation, in which case a retry is queued on a higher model on a new branch.
"""
import os
import selectors
import signal
import subprocess
import sys
import time
import re
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path

import fcntl
import threading

from claudarama.brief import build_brief
from claudarama.gate import OFFICE_ENV, write_turn_settings
from claudarama.session import TOKEN_ENV, mcp_config
from claudarama.worktrees import ticket_worktree
from claudarama.db import (
    ticket_from_thread,
    create_turn_token,
    get_queued_turns,
    get_thread,
    get_turn,
    grant_refusal,
    mark_turn_done,
    mark_turn_queued,
    mark_turn_failed,
    mark_turn_running,
    queue_turn,
    refuse_turn,
    requeue_running_turns,
    save_brief,
)


@dataclass
class TurnLaunch:
    """Everything a turn is started with. Built by ``Supervisor.build_launch``."""

    brief: str
    cmd: list[str]
    env: dict[str, str] | None = None  # None = inherit the supervisor's environment
    cwd: Path | None = None  # the ticket's worktree; None = where the office runs


@dataclass
class OrgSettings:
    resume_per_ticket: bool = False
    stall_timeout: float = 20 * 60
    escalate: bool = False
    escalation_model: str = "opus"
    concurrency: int = 3
    limit_fallback_minutes: float = 60
    batch_window_minutes: float = 2


def load_org_settings(pack_dir: Path) -> OrgSettings:
    """Read the health keys from ``org.yaml`` (flat ``key: value`` lines only)."""
    settings = OrgSettings()
    try:
        text = (pack_dir / "org.yaml").read_text(encoding="utf-8")
    except OSError:
        return settings
    for line in text.splitlines():
        key, sep, value = line.split("#", 1)[0].partition(":")
        key, value = key.strip(), value.strip()
        if not sep:
            continue
        if key == "stall_timeout_minutes":
            try:
                settings.stall_timeout = float(value) * 60
            except ValueError:
                pass  # keep default on a malformed value
        elif key == "escalate_stuck_turns":
            settings.escalate = value.lower() == "true"
        elif key == "resume_per_ticket":
            settings.resume_per_ticket = value.lower() == "true"
        elif key == "escalation_model" and value:
            settings.escalation_model = value
        elif key == "limit_fallback_minutes":
            try:
                settings.limit_fallback_minutes = float(value)
            except ValueError:
                pass
        elif key == "batch_window_minutes":
            try:
                settings.batch_window_minutes = float(value)
            except ValueError:
                pass
        elif key == "concurrency":
            try:
                settings.concurrency = int(value)
            except ValueError:
                pass
    return settings




def parse_reset(text: str) -> datetime | None:
    m = re.search(r'reset(?:s)?\s+(?:at|until)\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)', text, re.I)
    if not m:
        return None
    time_str = m.group(1).upper()
    try:
        if "AM" in time_str or "PM" in time_str:
            t = datetime.strptime(time_str.strip(), "%I:%M %p").time()
        else:
            t = datetime.strptime(time_str.strip(), "%H:%M").time()
        now = datetime.now()
        dt = datetime.combine(now.date(), t)
        if dt < now:
            dt += timedelta(days=1)
        return dt
    except ValueError:
        return None

def pause_machine(until: float) -> bool:
    path = Path.home() / ".claudarama" / "pause_until"
    was_paused = False
    try:
        was_paused = time.time() < float(path.read_text())
    except (OSError, ValueError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(until))
    return not was_paused

def is_machine_paused() -> bool:
    path = Path.home() / ".claudarama" / "pause_until"
    try:
        return time.time() < float(path.read_text())
    except (OSError, ValueError):
        return False

def notify_ceo(msg: str) -> None:
    subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Claudarama"'], capture_output=True)

def acquire_machine_slot(max_slots: int = 10) -> int:
    """Block until a machine slot is acquired. Returns file descriptor."""
    locks_dir = Path.home() / ".claudarama" / "machine_slots"
    locks_dir.mkdir(parents=True, exist_ok=True)
    
    # Create ticket for FIFO queue
    while True:
        ticket = locks_dir / f"wait-{time.time_ns()}-{os.getpid()}-{threading.get_ident()}"
        fd_ticket = os.open(ticket, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd_ticket, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            os.close(fd_ticket)
            time.sleep(0.01)

    try:
        while True:
            # Find the active first in line
            first_ticket = None
            for p in sorted(locks_dir.glob("wait-*")):
                if p == ticket:
                    if first_ticket is None:
                        first_ticket = ticket
                    continue
                try:
                    fd_check = os.open(p, os.O_RDWR)
                    try:
                        fcntl.flock(fd_check, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        os.unlink(p)
                        fcntl.flock(fd_check, fcntl.LOCK_UN)
                    except BlockingIOError:
                        if first_ticket is None:
                            first_ticket = p
                    finally:
                        os.close(fd_check)
                except OSError:
                    pass
            
            if first_ticket == ticket:
                for i in range(max_slots):
                    slot = locks_dir / f"slot-{i}.lock"
                    try:
                        fd_slot = os.open(slot, os.O_CREAT | os.O_RDWR)
                        fcntl.flock(fd_slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        return fd_slot
                    except (BlockingIOError, OSError):
                        try:
                            os.close(fd_slot)
                        except OSError:
                            pass
            time.sleep(0.2)
    finally:
        try:
            os.unlink(ticket)
        except OSError:
            pass
        os.close(fd_ticket)

def release_machine_slot(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except OSError:
        pass

class Supervisor:
    """Supervisor loop that executes headless turns.

    For each queued turn it builds a brief from pack files on disk (plus live
    thread history if this is a reply turn, i.e. ``thread`` is set), saves
    it, spawns ``claude -p`` and streams stdout to a ``.jsonl`` file.

    Sending a message mid-turn is handled by the office server's ``send`` MCP tool,
    which marks the turn done and queues the receiver's turn directly.  The
    supervisor does not manage that lifecycle; it only drives turns that are
    in the ``queued`` state.
    """

    def __init__(
        self,
        db_path: Path,
        pack_dir: Path,
        output_dir: Path,
        claude_binary: str = "claude",
        stall_timeout: float | None = None,
    ) -> None:
        self.db_path = db_path
        self.pack_dir = pack_dir
        self.output_dir = output_dir
        self.claude_binary = claude_binary
        self.stall_timeout_override = stall_timeout
        self._closed = threading.Event()
        self._procs: set[subprocess.Popen] = set()  # the turns running now
        self._procs_lock = threading.Lock()  # nothing is launched behind ``close``

    def _spawn(
        self, launch: TurnLaunch, output_file: Path, stall_timeout: float, mode: str = "w"
    ) -> str:
        """Run the launch command, streaming stdout to output_file and stderr beside it.

        Returns 'ok', 'crash' or 'stalled'; 'crash' without launching once the office is closed.
        """
        with open(output_file, mode, encoding="utf-8") as f, open(output_file.with_suffix(".stderr"), mode) as err:
            with self._procs_lock:
                if self._closed.is_set():
                    return "crash"
                proc = subprocess.Popen(
                    launch.cmd,
                    env=launch.env,
                    cwd=launch.cwd,
                    stdout=subprocess.PIPE,
                    stderr=err,
                    start_new_session=True,
                )
                self._procs.add(proc)
            sel = selectors.DefaultSelector()
            sel.register(proc.stdout, selectors.EVENT_READ)
            last_output = time.monotonic()
            try:
                while True:
                    remaining = stall_timeout - (time.monotonic() - last_output)
                    if remaining <= 0:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass  # exited just now; still counts as stalled
                        proc.wait()
                        return "stalled"
                    if not sel.select(timeout=remaining):
                        continue
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    f.write(chunk.decode("utf-8", errors="replace"))
                    f.flush()
                    last_output = time.monotonic()
                return "ok" if proc.wait() == 0 else "crash"
            finally:
                self._procs.discard(proc)
                sel.close()
                proc.stdout.close()

    def _create_branch(self, name: str) -> bool:
        res = subprocess.run(
            ["git", "-C", str(self.pack_dir.parent), "branch", name],
            capture_output=True,
        )
        return res.returncode == 0

    def build_launch(self, turn: dict, settings: OrgSettings | None = None) -> TurnLaunch:
        """Assemble the brief, ``claude`` command and environment for a turn. Spawns nothing."""
        # A reply turn gets the live thread from the messages table.
        thread = None
        ticket = None
        if turn.get("thread"):
            thread = get_thread(self.db_path, turn["thread"])
            ticket = ticket_from_thread(turn["thread"])

        working_note = None
        if ticket:
            from claudarama.db import get_working_note, is_ticket_hard
            working_note = get_working_note(self.db_path, turn["person_id"], ticket)
            turn["model"] = "opus" if is_ticket_hard(self.db_path, ticket) else "sonnet"

        brief = build_brief(pack_dir=self.pack_dir, role=turn["role"], thread=thread, ticket=ticket, working_note=working_note)
        if turn["branch"]:
            brief += f"\n\nWork on git branch `{turn['branch']}`.\n"

        token = create_turn_token(self.db_path, turn["id"])
        cmd = [
            # `claude -p` rejects stream-json without --verbose.
            self.claude_binary, "-p", brief, "--output-format", "stream-json", "--verbose",
            "--mcp-config", mcp_config(self.db_path, token),
            "--strict-mcp-config",
        ]
        if turn["model"]:
            cmd += ["--model", turn["model"]]

        if settings and settings.resume_per_ticket and ticket:
            from claudarama.db import get_ticket_conversation
            conversation_id = get_ticket_conversation(self.db_path, turn["person_id"], ticket)
            if conversation_id:
                cmd += ["-r", conversation_id]

        # One allowlist feeds both walls: native rules (unlisted calls denied) and the gate hook.
        settings_path = self.output_dir / f"{turn['id']}.settings.json"
        write_turn_settings(self.pack_dir, settings_path)
        cmd += ["--settings", str(settings_path), "--permission-mode", "dontAsk"]
        # The launcher's own token (the owner's, in the Session's server) stays out of the turn.
        env = {k: v for k, v in os.environ.items() if k != TOKEN_ENV}
        return TurnLaunch(brief=brief, cmd=cmd, env={**env, OFFICE_ENV: str(settings_path)})

    def _record_usage(self, turn_id: str, turn: dict, output_file: Path) -> None:
        if not output_file.exists():
            return
        import json
        from claudarama.db import save_turn_usage
        usage = None
        conversation_id = None
        model = None
        with open(output_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if "session_id" in data:
                        conversation_id = data["session_id"]
                    if "usage" in data:
                        usage = data["usage"]
                        if "cost" not in usage and "cost" in data:
                            usage["cost"] = data["cost"]
                    if "model" in data:
                        model = data["model"]
                except json.JSONDecodeError:
                    pass

        if usage:
            from claudarama.db import save_turn_usage
            save_turn_usage(self.db_path, turn_id, usage, model)

        ticket = ticket_from_thread(turn.get("thread"))
        if conversation_id and ticket:
            from claudarama.db import save_ticket_conversation
            save_ticket_conversation(self.db_path, turn["person_id"], ticket, conversation_id)

    def run_one_turn(self, turn_id: str) -> None:
        """Execute a single turn: build brief, spawn process, handle crash/stall."""
        turn = get_turn(self.db_path, turn_id)
        if turn is None:
            return

        reason = grant_refusal(self.db_path, turn)
        if reason:
            refuse_turn(self.db_path, turn_id, reason)
            return

        settings = load_org_settings(self.pack_dir)
        stall_timeout = (
            self.stall_timeout_override
            if self.stall_timeout_override is not None
            else settings.stall_timeout
        )

        # Every turn for a ticket runs in that ticket's worktree; made before the turn is given a token.
        ticket = ticket_from_thread(turn["thread"])
        worktree = ticket_worktree(self.pack_dir.parent, ticket) if ticket else None
        launch = self.build_launch(turn, settings)
        launch.cwd = worktree

        slot_fd = acquire_machine_slot(10)
        try:
            save_brief(self.db_path, turn_id, launch.brief)
            mark_turn_running(self.db_path, turn_id)
            output_file = self.output_dir / f"{turn_id}.jsonl"

            txt = ""
            def _check_limit() -> bool:
                nonlocal txt
                txt = output_file.read_text(encoding="utf-8", errors="replace") if output_file.exists() else ""
                return "session limit" in txt.lower() or "weekly limit" in txt.lower()

            error = ""
            try:
                outcome = self._spawn(launch, output_file, stall_timeout)
                if outcome == "crash" and not self._closed.is_set() and not _check_limit():
                    outcome = self._spawn(launch, output_file, stall_timeout, mode="a")
            except Exception as e:  # the launch command could not be started at all
                outcome, error = "crash", str(e)

            if self._closed.is_set() and outcome != "ok":
                return  # the Session closed mid-turn: left running, to be queued again at the next open

            self._record_usage(turn_id, turn, output_file)

            if outcome == "crash" and _check_limit():
                outcome = "limit"

            if outcome == "ok":
                mark_turn_done(self.db_path, turn_id)
                return

            if outcome == "limit":
                dt = parse_reset(txt)
                until = dt.timestamp() if dt else time.time() + settings.limit_fallback_minutes * 60
                if pause_machine(until):
                    notify_ceo("Paused for API limits")
                mark_turn_queued(self.db_path, turn_id)
                return

            # What `claude` wrote to stderr; failing that, the end of its transcript.
            stderr_file = output_file.with_suffix(".stderr")
            error = error or (stderr_file.read_text(errors="replace") if stderr_file.exists() else "")
            if outcome == "stalled":
                error = f"no output for {stall_timeout:g} seconds; killed\n{error}"
            mark_turn_failed(self.db_path, turn_id, (error.strip() or txt.strip())[-2000:])
            # ponytail: escalates once; an already-escalated turn just fails (no pause or notify yet).
            if (
                outcome == "stalled"
                and settings.escalate
                and turn["model"] != settings.escalation_model
            ):
                # A ticket has one branch, the one its worktree is on; the retry carries on there.
                branch = None if ticket else f"escalated/{turn_id[:8]}"
                if branch is None or self._create_branch(branch):
                    queue_turn(
                        self.db_path,
                        turn["person_id"],
                        thread=turn["thread"],
                        model=settings.escalation_model,
                        branch=branch,
                    )
        finally:
            release_machine_slot(slot_fd)

    def _run_turn(self, turn_id: str) -> None:
        """``run_one_turn``, except that a turn it cannot carry through fails with the reason
        rather than staying queued, to be tried again without end."""
        try:
            self.run_one_turn(turn_id)
        except Exception as e:
            mark_turn_failed(self.db_path, turn_id, f"{type(e).__name__}: {e}")

    def _launch_queued(self, busy: dict[str, threading.Thread]) -> None:
        """Start each queued turn the office's cap allows, one at a time for a Role.

        *busy* maps a Person to the thread on their turn.
        """
        if is_machine_paused():
            return
        cap = load_org_settings(self.pack_dir).concurrency
        for turn in get_queued_turns(self.db_path):
            if len(busy) >= cap:
                break
            if turn["person_id"] not in busy:
                thread = threading.Thread(target=self._run_turn, args=(turn["id"],), daemon=True)
                thread.start()
                busy[turn["person_id"]] = thread

    def poll(self) -> int:
        """Launch the queued turns the office's cap allows and wait for them. Returns the count of turns run."""
        busy: dict[str, threading.Thread] = {}
        self._launch_queued(busy)
        for thread in busy.values():
            thread.join()
        return len(busy)

    def run(self) -> None:
        """Run the office until ``close``: launch queued turns as the caps allow, each monitored to its end.

        Only one Session runs an office. A second waits on the office's lock, leaving the
        running office alone, and takes over when the first closes.
        """
        with open(self.db_path.with_name("office.lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # released when this process ends, however it ends
            requeue_running_turns(self.db_path)  # left by a Session that closed mid-turn
            busy: dict[str, threading.Thread] = {}
            while not self._closed.is_set():
                busy = {person: thread for person, thread in busy.items() if thread.is_alive()}
                try:
                    self._launch_queued(busy)
                except Exception as e:  # e.g. the database held by another process; the office keeps running
                    print(f"claudarama: could not launch queued turns: {e}", file=sys.stderr)
                self._closed.wait(0.5)

    def close(self) -> None:
        """Pause the office: launch nothing more and stop the turns that are running.

        A stopped turn stays running in the database; the next open queues it again.
        """
        # ponytail: runs when the Session closes cleanly. A server killed outright leaves its
        # turns' processes alive until the next open queues those turns again; reap them there if it bites.
        with self._procs_lock:
            self._closed.set()
            for proc in list(self._procs):  # a turn ending now drops itself from the set
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # exited just now

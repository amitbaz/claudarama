import sqlite3
from pathlib import Path

from claudarama.db import get_office_db_path, mandate_states, shown


def _usage(turns) -> str:
    return (
        f"{sum(t['input_tokens'] or 0 for t in turns)} in, {sum(t['output_tokens'] or 0 for t in turns)} out, "
        f"${sum(t['cost'] or 0 for t in turns):.2f}"
    )


def _mandate_report(conn: sqlite3.Connection, transcripts: Path, mandate: dict) -> list[str]:
    """Where the office did well on one Mandate and where it did not, from what it already stores:
    each Role that worked on it with its turns, numbered in the order the Mandate's turns were queued,
    then every Challenge of its Diagnosis, then every NO, FAIL, question and BLOCKED message in its
    tickets' threads, oldest first."""
    waiting = ", waiting for the CEO" if mandate["blocked_on_ceo"] else ""
    out = [f"\n--- Mandate {mandate['id']!r}: {mandate['status']}{waiting} ---"]
    turns = conn.execute(
        "SELECT t.* FROM turns t JOIN tickets k ON t.thread = 'ticket:' || k.id WHERE k.mandate_id = ? ORDER BY t.rowid",
        (mandate["id"],),
    ).fetchall()
    for role in dict.fromkeys(t["person_id"] for t in turns):  # in the order each Role first worked on it
        own = [(n, t) for n, t in enumerate(turns, 1) if t["person_id"] == role]
        out.append(f"{shown(role)}: {len(own)} turn{'s' * (len(own) != 1)}, {_usage([t for _, t in own])}")
        for n, t in own:
            ended = ": ".join(" ".join(part.split()) for part in (t["status"], t["refusal"], t["error"]) if part)
            transcript = transcripts / f"{t['id']}.jsonl"
            out.append(
                f"  turn {n} on {t['thread'].replace(':', ' ', 1)}: {ended}, {_usage([t])}, "
                + (f"transcript: {transcript}" if transcript.exists() else "no transcript")
            )
    for c in conn.execute(
        "SELECT c.*, m.investigator FROM challenges c JOIN mandates m ON m.id = c.mandate_id WHERE m.id = ? ORDER BY c.id",
        (mandate["id"],),
    ):
        out.append(
            f"Challenge {c['verdict']} from {shown(c['challenger'])} to {shown(c['investigator'])}: "
            + " ".join(f"{c['reasons']} What was run: {c['ran']}".split())
        )
    # A NO or a FAIL is addressed to the Role whose work it was.
    for m in conn.execute(
        "SELECT m.* FROM messages m JOIN tickets k ON m.thread = 'ticket:' || k.id "
        "WHERE k.mandate_id = ? AND m.msg_type IN ('NO', 'FAIL', 'QUESTION', 'BLOCKED') ORDER BY m.rowid",
        (mandate["id"],),
    ):
        out.append(
            f"{m['msg_type']} from {shown(m['sender'])} to {shown(m['receiver'])} on ticket {m['ticket']}: "
            + " ".join(m["body"].split())
        )
    return out


def status(db_path: Path) -> str:
    """What ``status`` shows of the office at *db_path*: its usage totals, then a report for each Mandate."""
    out: list[str] = []

    def _section(conn, title: str, query: str, prefix: str = ""):
        out.append(f"\n--- Usage by {title} ---")
        for r in conn.execute(query).fetchall():
            name = str(r['key'])
            if prefix and name.startswith(prefix):
                name = name.removeprefix(prefix)
            out.append(f"{name}: {r['i'] or 0} in, {r['o'] or 0} out, ${r['c'] or 0.0:.2f}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        _section(
            conn, "Person",
            "SELECT p.role || ' (' || p.name || ')' as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t JOIN people p ON t.person_id = p.id WHERE t.cost IS NOT NULL GROUP BY p.id"
        )

        _section(
            conn, "Ticket",
            "SELECT t.thread as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t WHERE t.thread LIKE 'ticket:%' AND t.cost IS NOT NULL GROUP BY t.thread",
            prefix="ticket:"
        )

        _section(
            conn, "Ritual",
            "SELECT t.thread as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t WHERE t.kind = 'ritual' AND t.cost IS NOT NULL GROUP BY t.thread",
            prefix="topic:"
        )

        for mandate in mandate_states(db_path):
            out += _mandate_report(conn, db_path.parent / "turns", mandate)

    return "\n".join(out)


def print_status(project_name: str | None = None) -> int:
    db_path = get_office_db_path(project_name)
    if not db_path.exists():
        print("No office.db found.")
        return 1
    print(status(db_path))
    return 0

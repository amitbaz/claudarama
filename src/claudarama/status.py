import sqlite3
from pathlib import Path
from claudarama.db import get_office_db_path

def print_status(project_name: str | None = None) -> int:
    db_path = get_office_db_path(project_name)
    if not db_path.exists():
        print("No office.db found.")
        return 1
        
    def _print_section(conn, title: str, query: str, prefix: str = ""):
        print(f"\n--- Usage by {title} ---")
        for r in conn.execute(query).fetchall():
            name = str(r['key'])
            if prefix and name.startswith(prefix):
                name = name.removeprefix(prefix)
            print(f"{name}: {r['i'] or 0} in, {r['o'] or 0} out, ${r['c'] or 0.0:.2f}")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        _print_section(
            conn, "Person",
            "SELECT p.name as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t JOIN people p ON t.person_id = p.id WHERE t.cost IS NOT NULL GROUP BY p.name"
        )
            
        _print_section(
            conn, "Ticket",
            "SELECT t.thread as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t WHERE t.thread LIKE 'ticket:%' AND t.cost IS NOT NULL GROUP BY t.thread",
            prefix="ticket:"
        )
            
        _print_section(
            conn, "Ritual",
            "SELECT t.thread as key, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c "
            "FROM turns t WHERE t.kind = 'ritual' AND t.cost IS NOT NULL GROUP BY t.thread",
            prefix="topic:"
        )

    return 0

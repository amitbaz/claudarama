import sqlite3
from pathlib import Path
from claudarama.db import get_office_db_path

def print_status(project_name: str | None = None) -> int:
    db_path = get_office_db_path(project_name)
    if not db_path.exists():
        print("No office.db found.")
        return 1
        
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        print("--- Usage by Person ---")
        rows = conn.execute("SELECT p.name, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c FROM turns t JOIN people p ON t.person_id = p.id WHERE t.cost IS NOT NULL GROUP BY p.name").fetchall()
        for r in rows:
            print(f"{r['name']}: {r['i'] or 0} in, {r['o'] or 0} out, ${r['c'] or 0.0:.2f}")
            
        print("\n--- Usage by Ticket ---")
        rows = conn.execute("SELECT t.thread, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c FROM turns t WHERE t.thread LIKE 'ticket:%' AND t.cost IS NOT NULL GROUP BY t.thread").fetchall()
        for r in rows:
            ticket = r['thread'].removeprefix("ticket:")
            print(f"{ticket}: {r['i'] or 0} in, {r['o'] or 0} out, ${r['c'] or 0.0:.2f}")
            
        print("\n--- Usage by Ritual ---")
        rows = conn.execute("SELECT t.thread, sum(t.input_tokens) as i, sum(t.output_tokens) as o, sum(t.cost) as c FROM turns t WHERE t.kind = 'ritual' AND t.cost IS NOT NULL GROUP BY t.thread").fetchall()
        for r in rows:
            ritual = r['thread'].removeprefix("topic:") if r['thread'] and r['thread'].startswith("topic:") else str(r['thread'])
            print(f"{ritual}: {r['i'] or 0} in, {r['o'] or 0} out, ${r['c'] or 0.0:.2f}")

    return 0

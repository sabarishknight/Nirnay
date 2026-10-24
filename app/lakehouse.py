"""Lakehouse plumbing shared by the local stand-in (SQLite) and BigQuery.

- infer_schema(): column types for each raw CSV (also written out as BigQuery JSON schemas)
- build_local(): loads the raw CSVs into SQLite databases named like the BigQuery datasets and runs
  the same curated/gold SQL files, so the pipeline is tested locally before it runs in BigQuery
- render_sql(): substitutes snapshot constants and, for SQLite, rewrites CREATE OR REPLACE TABLE
"""
import csv, json, os, re, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "out", "raw")
SQL_DIR = os.path.join(ROOT, "sql")
DATASETS = ("lending_raw", "lending_curated", "lending_gold")
SNAPSHOT = {"M3": "2026-07", "M6": "2026-04"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _type_of(values):
    vals = [v for v in values if v != ""]
    if not vals:
        return "STRING"
    if all(DATE_RE.match(v) for v in vals):
        return "DATE"
    try:
        [int(v) for v in vals]
        if any(len(v.lstrip("-")) > 1 and v.lstrip("-").startswith("0") for v in vals):
            return "STRING"
        return "INT64"
    except ValueError:
        pass
    try:
        [float(v) for v in vals]
        return "FLOAT64"
    except ValueError:
        return "STRING"


def infer_schema(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    return [(h, _type_of([r[i] for r in body])) for i, h in enumerate(header)]


def raw_tables():
    return sorted(f[:-4] for f in os.listdir(RAW_DIR) if f.endswith(".csv"))


def write_bq_schemas(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for t in raw_tables():
        sch = infer_schema(os.path.join(RAW_DIR, t + ".csv"))
        json.dump([{"name": n, "type": ty, "mode": "NULLABLE"} for n, ty in sch], open(os.path.join(out_dir, t + ".json"), "w"), indent=1)


def render_sql(text, dialect):
    for k, v in SNAPSHOT.items():
        text = text.replace("{" + k + "}", v)
    stmts = [s.strip() for s in re.split(r";\s*(?:\n|$)", text) if s.strip() and not all(l.strip().startswith("--") or not l.strip() for l in s.strip().splitlines())]
    out = []
    for s in stmts:
        if dialect == "sqlite":
            m = re.match(r"(?is)^(?:--[^\n]*\n\s*)*CREATE OR REPLACE TABLE\s+([\w.]+)\s+AS\s+(.*)$", s)
            if m:
                out.append(f"DROP TABLE IF EXISTS {m.group(1)}")
                out.append(f"CREATE TABLE {m.group(1)} AS {m.group(2)}")
                continue
        out.append(s)
    return out


def _cast(v, ty):
    if v == "":
        return None
    if ty == "INT64":
        return int(v)
    if ty == "FLOAT64":
        return float(v)
    return v


def connect_local(db_dir):
    con = sqlite3.connect(os.path.join(db_dir, "main.db"), check_same_thread=False)
    for ds in DATASETS:
        con.execute(f"ATTACH DATABASE '{os.path.join(db_dir, ds + '.db')}' AS {ds}")
    con.row_factory = sqlite3.Row
    return con


def build_local(db_dir):
    os.makedirs(db_dir, exist_ok=True)
    for ds in DATASETS + ("main",):
        p = os.path.join(db_dir, ds + ".db")
        if os.path.exists(p):
            os.remove(p)
    con = connect_local(db_dir)
    for t in raw_tables():
        path = os.path.join(RAW_DIR, t + ".csv")
        sch = infer_schema(path)
        sqlt = {"INT64": "INTEGER", "FLOAT64": "REAL"}
        con.execute(f"CREATE TABLE lending_raw.{t} (" + ", ".join(f"{n} {sqlt.get(ty, 'TEXT')}" for n, ty in sch) + ")")
        with open(path) as f:
            r = csv.reader(f)
            next(r)
            con.executemany(f"INSERT INTO lending_raw.{t} VALUES ({','.join('?' * len(sch))})", ([_cast(v, sch[i][1]) for i, v in enumerate(row)] for row in r))
    for fn in sorted(os.listdir(SQL_DIR)):
        if fn[:2].isdigit() and fn.endswith(".sql"):
            for s in render_sql(open(os.path.join(SQL_DIR, fn)).read(), "sqlite"):
                con.execute(s)
    # live tables written by the app (BigQuery creates these at deploy time)
    con.execute("CREATE TABLE IF NOT EXISTS lending_gold.agent_audit (run_id TEXT, application_id TEXT, ts TEXT, step TEXT, event_type TEXT, detail TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS lending_gold.officer_decisions (application_id TEXT, decided_at TEXT, agent_recommendation TEXT, officer_decision TEXT, override INTEGER, override_reason TEXT, decided_by TEXT, run_id TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS lending_raw.ext_api_log (run_id TEXT, ts TEXT, service TEXT, request_key TEXT, latency_ms INTEGER, cost_inr REAL, response TEXT)")
    con.commit()
    return con


if __name__ == "__main__":
    import sys
    con = build_local(sys.argv[1] if len(sys.argv) > 1 else "/tmp/nirnay_db")
    for ds in DATASETS:
        for (name,) in con.execute(f"SELECT name FROM {ds}.sqlite_master WHERE type='table'"):
            n = con.execute(f"SELECT COUNT(*) FROM {ds}.{name}").fetchone()[0]
            print(f"{ds}.{name}: {n}")

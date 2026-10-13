"""Local analytical warehouse and automatic demo-data bootstrap.

DuckDB is the source of truth. On a new installation this module generates
the synthetic incidents in memory and persists them directly into DuckDB;
there is no required CSV dataset at runtime. Application code reads only the
canonical semantic view, never the raw warehouse table.
"""
from pathlib import Path
from threading import Lock

import duckdb
import pandas as pd

APP_DIR = Path(__file__).resolve().parent
WAREHOUSE_DIR = APP_DIR / "warehouse"
DATABASE_PATH = WAREHOUSE_DIR / "incident_analytics.duckdb"
_LOCK = Lock()


def _connection(read_only: bool = False):
    WAREHOUSE_DIR.mkdir(exist_ok=True)
    return duckdb.connect(str(DATABASE_PATH), read_only=read_only)


def ensure_warehouse(force: bool = False) -> None:
    """Create the warehouse and its demo data automatically when needed."""
    # Normal MCP requests run in separate local processes. Once a healthy
    # warehouse exists they must not take a write lock just to verify it:
    # DuckDB supports concurrent read-only connections, but Windows prevents a
    # concurrent read/write open of the same database file.
    if not force and DATABASE_PATH.exists():
        con = _connection(read_only=True)
        try:
            raw_exists = con.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'main' AND table_name = 'raw_incidents'
            """).fetchone()[0]
            view_exists = con.execute("""
                SELECT COUNT(*) FROM information_schema.views
                WHERE table_schema = 'main' AND table_name = 'semantic_incidents'
            """).fetchone()[0]
            if raw_exists and view_exists:
                return
        finally:
            con.close()

    with _LOCK:
        con = _connection()
        try:
            table_exists = bool(con.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'main' AND table_name = 'raw_incidents'
            """).fetchone()[0])
            if force or not table_exists:
                # Synthetic data is generated in memory, then stored directly
                # in DuckDB. No CSV is required to start or operate the app.
                from .dataset_generator import generate_incidents

                # DuckDB's pandas bridge currently expects object strings
                # rather than pandas 3's dedicated ``str`` dtype.
                generated = pd.DataFrame(generate_incidents(n=5000), dtype=object)
                con.execute("DROP TABLE IF EXISTS raw_incidents")
                con.register("generated_incidents", generated)
                con.execute("CREATE TABLE raw_incidents AS SELECT * FROM generated_incidents")
                con.unregister("generated_incidents")
            con.execute("""
                CREATE OR REPLACE VIEW semantic_incidents AS
                SELECT
                    incident_id, title, application, environment, region, severity, status,
                    category, assigned_team, reporter, root_cause, reported_at, resolved_at,
                    TRY_CAST(reported_at AS TIMESTAMP) AS reported_at_ts,
                    TRY_CAST(resolved_at AS TIMESTAMP) AS resolved_at_ts,
                    TRY_CAST(resolution_hours AS DOUBLE) AS resolution_hours
                FROM raw_incidents
            """)
        finally:
            con.close()


def incidents_dataframe() -> pd.DataFrame:
    ensure_warehouse()
    con = _connection()
    try:
        return con.execute("SELECT * FROM semantic_incidents").fetchdf()
    finally:
        con.close()


def query_semantic(sql: str, parameters: list | None = None) -> pd.DataFrame:
    """Execute a read-only query against the semantic view, never raw tables."""
    cleaned = sql.strip().rstrip(";")
    if not cleaned.lower().startswith(("select", "with")):
        raise ValueError("Only read-only SELECT queries are allowed")
    if "raw_incidents" in cleaned.lower():
        raise ValueError("Query the semantic_incidents view, not raw warehouse tables")
    ensure_warehouse()
    con = _connection(read_only=True)
    try:
        return con.execute(cleaned, parameters or []).fetchdf()
    finally:
        con.close()


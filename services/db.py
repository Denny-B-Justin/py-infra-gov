"""
Database access layer.

* Production: Azure Databricks Unity Catalog through a SQL Warehouse, using a
  service principal (OAuth M2M). Traffic is TLS-encrypted end to end and the
  connector verifies the server certificate (never disabled here).
* Development: a local SQLite file with the same logical schema.

Every statement is PARAMETERISED (``:name`` placeholders bound by the driver).
The only strings ever concatenated into SQL are the validated table-name
constants from ``constants.T`` and column names that are hard-coded in this
code base — never user input. ``_check_ident`` enforces that at runtime.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import constants as C

log = logging.getLogger("infragov.db")

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_FQ_TABLE = re.compile(r"^(`[A-Za-z0-9_]+`\.){2}`[A-Za-z0-9_]+`$|^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Refusing unsafe SQL identifier: {name!r}")
    return name


def _check_table(name: str) -> str:
    if name not in C.T.values() or not _FQ_TABLE.match(name):
        raise ValueError(f"Unknown table: {name!r}")
    return name


def utcnow() -> datetime:
    """Naive UTC timestamp, millisecond precision (stored as UC TIMESTAMP)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def to_iso(value: Any) -> str:
    """Normalise a DB timestamp (datetime or ISO string) to ISO-8601 'Z'."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat(timespec="milliseconds") + "Z"
    if isinstance(value, date):
        return value.isoformat()
    s = str(value)
    return s if s.endswith("Z") or "+" in s[10:] else (s.replace(" ", "T") + "Z")


def parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)
    s = str(value).replace("Z", "").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def jdump(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False, separators=(",", ":"))


def jload(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return [] if default is None else default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return [] if default is None else default


def in_clause(prefix: str, values: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Build a parameterised IN (...) list: ('(:p0,:p1)', {'p0':..,'p1':..})."""
    _check_ident(prefix)
    vals = list(values)
    if not vals:
        return "(NULL)", {}
    names = [f"{prefix}{i}" for i in range(len(vals))]
    return "(" + ",".join(f":{n}" for n in names) + ")", dict(zip(names, vals))


class Database:
    """Thin, parameter-only wrapper over Databricks SQL / SQLite."""

    def __init__(self) -> None:
        self.backend = C.DB_BACKEND
        self._local = threading.local()
        self._sqlite_lock = threading.RLock()
        if self.backend == "sqlite":
            Path(C.SQLITE_PATH).parent.mkdir(parents=True, exist_ok=True)
            from services.schema import SQLITE_DDL

            with self._sqlite() as conn:
                conn.executescript(SQLITE_DDL)

    # ------------------------------------------------------------------ conn
    @contextmanager
    def _sqlite(self):
        with self._sqlite_lock:
            conn = sqlite3.connect(C.SQLITE_PATH, timeout=30, detect_types=0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _databricks_conn(self):
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        from databricks import sql as dbsql
        from databricks.sdk.core import Config

        host = C.DATABRICKS_SERVER_HOSTNAME.replace("https://", "").rstrip("/")

        def credentials_provider():
            if C.DATABRICKS_AUTH_TYPE == "azure-client-secret":
                from databricks.sdk.core import azure_service_principal

                cfg = Config(
                    host=f"https://{host}",
                    azure_client_id=C.DATABRICKS_CLIENT_ID,
                    azure_client_secret=C.DATABRICKS_CLIENT_SECRET,
                    azure_tenant_id=C.AZURE_TENANT_ID,
                )
                return azure_service_principal(cfg)
            from databricks.sdk.core import oauth_service_principal

            cfg = Config(
                host=f"https://{host}",
                client_id=C.DATABRICKS_CLIENT_ID,
                client_secret=C.DATABRICKS_CLIENT_SECRET,
            )
            return oauth_service_principal(cfg)

        conn = dbsql.connect(
            server_hostname=host,
            http_path=C.DATABRICKS_HTTP_PATH,
            credentials_provider=credentials_provider,
            catalog=C.UC_CATALOG,
            schema=C.UC_SCHEMA,
            user_agent_entry="infragov-dash",
        )
        self._local.conn = conn
        return conn

    def _reset_databricks(self) -> None:
        conn = getattr(self._local, "conn", None)
        self._local.conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- public
    def query(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = self._clean(params)
        if self.backend == "sqlite":
            with self._sqlite() as conn:
                cur = conn.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
        for attempt in (1, 2):
            try:
                with self._databricks_conn().cursor() as cur:
                    cur.execute(sql, parameters=params)
                    if cur.description is None:
                        return []
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception as exc:  # noqa: BLE001
                self._reset_databricks()
                if attempt == 2:
                    log.error("Databricks query failed: %s", type(exc).__name__)
                    raise
        return []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        params = self._clean(params)
        if self.backend == "sqlite":
            with self._sqlite() as conn:
                conn.execute(sql, params)
            return
        for attempt in (1, 2):
            try:
                with self._databricks_conn().cursor() as cur:
                    cur.execute(sql, parameters=params)
                return
            except Exception as exc:  # noqa: BLE001
                self._reset_databricks()
                if attempt == 2:
                    log.error("Databricks statement failed: %s", type(exc).__name__)
                    raise

    def one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, row: dict[str, Any]) -> None:
        _check_table(table)
        cols = [_check_ident(c) for c in row]
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"
        self.execute(sql, row)

    def update(self, table: str, values: dict[str, Any], where: dict[str, Any]) -> None:
        _check_table(table)
        sets = ", ".join(f"{_check_ident(c)} = :v_{c}" for c in values)
        conds = " AND ".join(f"{_check_ident(c)} = :w_{c}" for c in where)
        params = {f"v_{k}": v for k, v in values.items()}
        params.update({f"w_{k}": v for k, v in where.items()})
        self.execute(f"UPDATE {table} SET {sets} WHERE {conds}", params)

    def delete(self, table: str, where: dict[str, Any]) -> None:
        _check_table(table)
        if not where:
            raise ValueError("Refusing DELETE without WHERE")
        conds = " AND ".join(f"{_check_ident(c)} = :w_{c}" for c in where)
        self.execute(f"DELETE FROM {table} WHERE {conds}", {f"w_{k}": v for k, v in where.items()})

    def upsert(self, table: str, keys: Iterable[str], row: dict[str, Any], insert_only: Iterable[str] = ()) -> None:
        """Insert or update on the given natural key (MERGE on Databricks)."""
        _check_table(table)
        keys = [_check_ident(k) for k in keys]
        cols = [_check_ident(c) for c in row]
        insert_only = set(insert_only)
        updatable = [c for c in cols if c not in keys and c not in insert_only]
        if self.backend == "sqlite":
            sql = (
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
                f"ON CONFLICT ({', '.join(keys)}) DO "
                + (f"UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in updatable)}" if updatable else "NOTHING")
            )
            self.execute(sql, row)
            return
        src = ", ".join(f":{c} AS {c}" for c in cols)
        on = " AND ".join(f"t.{k} = s.{k}" for k in keys)
        sql = f"MERGE INTO {table} AS t USING (SELECT {src}) AS s ON {on} "
        if updatable:
            sql += f"WHEN MATCHED THEN UPDATE SET {', '.join(f't.{c} = s.{c}' for c in updatable)} "
        sql += f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join('s.' + c for c in cols)})"
        self.execute(sql, row)

    # --------------------------------------------------------------- helpers
    def _clean(self, params: dict[str, Any] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in (params or {}).items():
            _check_ident(k)
            if self.backend == "sqlite":
                if isinstance(v, datetime):
                    v = v.isoformat(sep=" ", timespec="milliseconds")
                elif isinstance(v, bool):
                    v = 1 if v else 0
            out[k] = v
        return out


_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
    return _db

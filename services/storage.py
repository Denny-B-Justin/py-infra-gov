"""
Binary file storage for source documents.

Production: Unity Catalog Volume (replaces the private Supabase Storage bucket
"assessment-documents") via the Databricks Files API over HTTPS, using the
same service principal as the SQL connection. Files are never served
directly — downloads go through an authorised Flask route.

Development: a local folder outside the web-served `assets/` directory.
"""
from __future__ import annotations

import io
import os
import threading
from pathlib import Path

import constants as C

_client = None
_lock = threading.Lock()


def _workspace():
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                from databricks.sdk import WorkspaceClient

                host = "https://" + C.DATABRICKS_SERVER_HOSTNAME.replace("https://", "").rstrip("/")
                if C.DATABRICKS_AUTH_TYPE == "azure-client-secret":
                    _client = WorkspaceClient(
                        host=host,
                        azure_client_id=C.DATABRICKS_CLIENT_ID,
                        azure_client_secret=C.DATABRICKS_CLIENT_SECRET,
                        azure_tenant_id=C.AZURE_TENANT_ID,
                    )
                else:
                    _client = WorkspaceClient(
                        host=host,
                        client_id=C.DATABRICKS_CLIENT_ID,
                        client_secret=C.DATABRICKS_CLIENT_SECRET,
                    )
    return _client


def _local_path(rel: str) -> Path:
    root = Path(C.LOCAL_STORAGE_DIR).resolve()
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise ValueError("Path traversal blocked")
    return p


def _volume_path(rel: str) -> str:
    rel = rel.lstrip("/")
    if ".." in rel.split("/"):
        raise ValueError("Path traversal blocked")
    return f"{C.UC_VOLUME_PATH}/{rel}"


def put(rel: str, data: bytes) -> None:
    if C.DB_BACKEND == "sqlite":
        p = _local_path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        os.chmod(p, 0o600)
        return
    _workspace().files.upload(_volume_path(rel), io.BytesIO(data), overwrite=True)


def get(rel: str) -> bytes:
    if C.DB_BACKEND == "sqlite":
        return _local_path(rel).read_bytes()
    resp = _workspace().files.download(_volume_path(rel))
    return resp.contents.read()


def delete(rel: str) -> None:
    try:
        if C.DB_BACKEND == "sqlite":
            _local_path(rel).unlink(missing_ok=True)
            return
        _workspace().files.delete(_volume_path(rel))
    except Exception:  # noqa: BLE001 - best effort, row deletion still proceeds
        pass

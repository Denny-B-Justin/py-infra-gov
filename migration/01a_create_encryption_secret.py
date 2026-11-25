"""
One-off notebook cell (Python) — create FIELD_ENCRYPTION_KEY as a Databricks secret.

Run once, before 01b_json_to_uc_table.py. It generates a fresh AES-256 key
(same format as `python manage.py gen-keys`), stores it in the secret scope that
01b reads, and prints it ONCE so you can copy it into:
  * Posit Connect → the content's Vars panel → FIELD_ENCRYPTION_KEY (mark it secret)
  * your password manager (lose it and the encrypted fields cannot be read again)
  * your local .env, if you run manage.py against Databricks
Then clear this cell's output (cell menu → Clear output).

Re-running is safe: if the secret already exists it is left untouched and not
shown. Only set REPLACE_EXISTING = True before any data has been loaded with
the current key — replacing it afterwards makes that data unreadable.
"""
import base64
import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import ResourceAlreadyExists

dbutils.widgets.text("secret_scope", "infragov", "Secret scope")  # noqa: F821 - same widget the 01b cell reads
SCOPE, KEY = dbutils.widgets.get("secret_scope").strip(), "FIELD_ENCRYPTION_KEY"  # noqa: F821
REPLACE_EXISTING = False  # deliberately not a widget: replacing the key after loading data makes it unreadable

w = WorkspaceClient()  # authenticates as you, the notebook user
try:
    w.secrets.create_scope(scope=SCOPE)
    print(f"created secret scope {SCOPE!r} (you have MANAGE on it; nobody else can read it)")
except ResourceAlreadyExists:
    print(f"secret scope {SCOPE!r} already exists")

if any(s.key == KEY for s in w.secrets.list_secrets(scope=SCOPE)) and not REPLACE_EXISTING:
    print(f"{SCOPE}/{KEY} already exists - left unchanged. Nothing to do.")
else:
    field_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    w.secrets.put_secret(scope=SCOPE, key=KEY, string_value=field_key)
    print(f"stored {SCOPE}/{KEY}. Copy it now to Posit Connect Vars and your password manager, then clear this output:\n")
    print(f"FIELD_ENCRYPTION_KEY={field_key}")

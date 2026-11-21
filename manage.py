"""
Operational commands.

  python manage.py gen-keys                 # print fresh SECRET_KEY / FIELD_ENCRYPTION_KEY
  python manage.py print-uc-ddl             # Unity Catalog DDL (migration/01_create_uc_tables.sql)
  python manage.py create-admin EMAIL NAME  # first Admin (prompts for password, never echoes it)
  python manage.py seed-demo                # LOCAL SQLITE ONLY: demo users + data for development
"""
from __future__ import annotations

import getpass
import secrets
import sys

import constants as C


def gen_keys() -> None:
    from services.crypto import generate_field_key

    print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
    print(f"FIELD_ENCRYPTION_KEY={generate_field_key()}")


def create_admin(email: str, name: str, password: str | None = None) -> str:
    from services import auth
    from services.db import get_db, utcnow
    from services.validators import new_uuid, password_policy_errors, validate_email

    email = validate_email(email)
    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm: "):
            sys.exit("Passwords do not match.")
    errs = password_policy_errors(password, email, name)
    if errs:
        sys.exit(" ".join(errs))
    db = get_db()
    existing = auth.get_user_by_email(email)
    now = utcnow()
    if existing:
        db.update(C.T["users"], {"role": C.ROLE_ADMIN, "password_hash": auth.hash_password(password), "updated_at": now}, {"id": existing["id"]})
        return existing["id"]
    uid = new_uuid()
    db.insert(C.T["users"], {
        "id": uid, "email": email, "password_hash": auth.hash_password(password), "name": name, "organisation": "", "country": "",
        "job_title": "", "phone": "", "role": C.ROLE_ADMIN, "pref_email_notifications": True, "pref_weekly_digest": True,
        "pref_invite_notifications": True, "pref_publication_notifications": True, "is_active": True, "email_confirmed_at": now,
        "failed_login_count": 0, "locked_until": None, "last_login_at": None, "password_changed_at": now, "created_at": now, "updated_at": now,
    })
    return uid


def seed_demo() -> None:
    if C.DB_BACKEND != "sqlite":
        sys.exit("seed-demo only runs against the local SQLite backend.")
    import flask

    from services import auth, repository
    from services.db import get_db, utcnow
    from services.validators import new_uuid

    pw = "Demo-Passw0rd!x"
    admin_id = create_admin("admin@example.org", "Ada Admin", pw)
    db = get_db()
    now = utcnow()

    def mk(email, name, role, org):
        u = auth.get_user_by_email(email)
        if u:
            return u["id"]
        uid = new_uuid()
        db.insert(C.T["users"], {
            "id": uid, "email": email, "password_hash": auth.hash_password(pw), "name": name, "organisation": org, "country": "Serbia",
            "job_title": "", "phone": "", "role": role, "pref_email_notifications": True, "pref_weekly_digest": True,
            "pref_invite_notifications": True, "pref_publication_notifications": True, "is_active": True, "email_confirmed_at": now,
            "failed_login_count": 0, "locked_until": None, "last_login_at": None, "password_changed_at": now, "created_at": now, "updated_at": now,
        })
        return uid

    owner_id = mk("owner@example.org", "Olivia Owner", C.ROLE_OWNER, "Ministry of Finance")
    contrib_id = mk("contrib@example.org", "Carlos Contributor", C.ROLE_VIEWER, "PIM Unit")
    mk("viewer@example.org", "Vera Viewer", C.ROLE_VIEWER, "Audit Office")
    owner = auth._user_public(auth.get_user_by_id(owner_id))
    app = flask.Flask("seed")
    with app.test_request_context():
        if not db.query(f"SELECT id FROM {C.T['assessments']}"):
            aid = repository.create_assessment(owner, kind="infragov", country="Serbia", fiscal_year="2025", department="Ministry of Finance", description="Demo")
            levels = list(C.MATURITY_LEVELS)
            for dim in (1, 2, 3):
                meta = repository.F.dimension_meta("infragov", dim)
                for i in range(1, meta["mbiCount"] + 1):
                    repository.save_mbi_entry(owner, aid, dim, i, {
                        "keyRespondents": ["PIM Department"], "dataSource": "PIM Guidelines 2025, s.3",
                        "resultSummary": f"Demo finding for D{dim}.{i}.", "resultDetail": "Internal notes.",
                        "maturityBenchmark": levels[(dim + i) % 4]})
                if dim < 3:
                    repository.publish_dimension(owner, aid, dim)
            repository.assign_user_to_dimensions(owner, aid, [3, 4], "contrib@example.org", "", "PIM Unit", "Contributor")
            aid2 = repository.create_assessment(auth._user_public(auth.get_user_by_id(admin_id)), kind="infragov", country="Albania",
                                                fiscal_year="2025", department="MoF", description="")
            admin = auth._user_public(auth.get_user_by_id(admin_id))
            meta = repository.F.dimension_meta("infragov", 1)
            for i in range(1, meta["mbiCount"] + 1):
                repository.save_mbi_entry(admin, aid2, 1, i, {"keyRespondents": ["Treasury"], "dataSource": "Budget law", "resultSummary": "Demo.",
                                                              "maturityBenchmark": levels[i % 4]})
            repository.publish_dimension(admin, aid2, 1)
    print(f"Seeded. Users: admin@ / owner@ / contrib@ / viewer@example.org — password: {pw}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "gen-keys":
        gen_keys()
    elif cmd == "print-uc-ddl":
        from services.schema import uc_ddl

        print(uc_ddl())
    elif cmd == "create-admin" and len(sys.argv) >= 4:
        print("Admin user id:", create_admin(sys.argv[2], " ".join(sys.argv[3:])))
    elif cmd == "seed-demo":
        seed_demo()
    else:
        print(__doc__)

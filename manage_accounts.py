"""Command-line account tools for CampusHub (run from the project folder, venv active).

    python manage_accounts.py create-admin      first administrator login (asks for e-mail + password)
    python manage_accounts.py reset-admin       new password for an administrator who is locked out
    python manage_accounts.py demo-logins       DEMO ONLY: one shared password for everyone without a login
    python manage_accounts.py status            how many accounts exist

Needs sql/07_add_user_accounts.sql to have been run. Uses the same .env as the app.
Passwords are typed without being shown and stored only as salted scrypt hashes.
"""
import getpass
import sys
from datetime import datetime

import auth as A
import db
import queries as Q

DEMO_PASSWORD = "Campus@2026"


def _ask_password():
    while True:
        pw = getpass.getpass("New password (not shown): ")
        problems = A.password_problems(pw)
        if problems:
            print("  The password needs " + " and ".join(problems) + ".")
            continue
        if getpass.getpass("Repeat it: ") != pw:
            print("  The two passwords do not match. Try again.")
            continue
        return pw


def _pick_admin(with_account):
    rows = db.query("""SELECT a.admin_id, a.name, a.email, a.role, ua.account_id
                       FROM admin a LEFT JOIN user_account ua ON ua.admin_id = a.admin_id ORDER BY a.admin_id""")
    rows = [r for r in rows if bool(r["account_id"]) == with_account]
    if not rows:
        print("No administrators " + ("with" if with_account else "without") + " a login were found.")
        return None
    for r in rows:
        print(f"  {r['email']:<40} {r['name']} ({r['role'].replace('_', ' ').lower()})")
    email = input("E-mail of the administrator: ").strip().lower()
    match = [r for r in rows if r["email"].lower() == email]
    if not match:
        print("That e-mail is not in the list above.")
        return None
    return match[0]


def create_admin():
    admin = _pick_admin(with_account=False)
    if not admin:
        return 1
    pw = _ask_password()
    Q.create_account("ADMIN", admin["admin_id"], A.hash_password(pw), False, datetime.now())
    print(f"Done. {admin['name']} can now sign in as Admin with {admin['email']}.")
    return 0


def reset_admin():
    admin = _pick_admin(with_account=True)
    if not admin:
        return 1
    pw = _ask_password()
    Q.set_password(admin["account_id"], A.hash_password(pw), False, datetime.now())
    Q.set_account_active(admin["account_id"], True)
    print(f"Done. {admin['name']} has a new password and the account is active and unlocked.")
    return 0


def demo_logins():
    print("DEMO ONLY: every student, faculty member and administrator WITHOUT a login gets one,")
    print(f"all with the same password '{DEMO_PASSWORD}'. Anyone who knows it can sign in as anyone.")
    print("Use this on your own laptop for the review, never on a shared or public server.")
    if input("Type DEMO to continue: ").strip() != "DEMO":
        print("Nothing changed.")
        return 1
    shared_hash = A.hash_password(DEMO_PASSWORD)     # hashed once; fine for throw-away demo logins
    now = datetime.now()
    made = {}
    for role, table, pid in (("STUDENT", "student", "student_id"), ("FACULTY", "faculty", "faculty_id"),
                             ("ADMIN", "admin", "admin_id")):
        ids = [r["id"] for r in db.query(f"""SELECT p.{pid} AS id FROM {table} p
                                              LEFT JOIN user_account ua ON ua.{pid} = p.{pid}
                                              WHERE ua.account_id IS NULL ORDER BY p.{pid}""")]
        for person_id in ids:
            Q.create_account(role, person_id, shared_hash, False, now)
        made[role] = len(ids)
    print(f"Created {made['STUDENT']} student, {made['FACULTY']} faculty and {made['ADMIN']} admin logins.")
    examples = {
        "Student": db.one("SELECT registration_no AS login, name FROM student ORDER BY student_id LIMIT 1"),
        "Faculty": db.one("SELECT employee_code AS login, name FROM faculty ORDER BY faculty_id LIMIT 1"),
        "Admin":   db.one("SELECT email AS login, name FROM admin ORDER BY admin_id LIMIT 1"),
    }
    print("\nTry these on the sign-in page (password " + DEMO_PASSWORD + "):")
    for label, r in examples.items():
        if r:
            print(f"  {label:<8} {r['login']:<34} ({r['name']})")
    return 0


def status():
    s = Q.account_summary()
    print(f"{s['total'] or 0} accounts: {s['students'] or 0} students, {s['faculty'] or 0} faculty, "
          f"{s['admins'] or 0} admins; {s['disabled'] or 0} disabled; {s['must_change'] or 0} with a temporary password.")
    return 0


COMMANDS = {"create-admin": create_admin, "reset-admin": reset_admin, "demo-logins": demo_logins, "status": status}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(COMMANDS[sys.argv[1]]())
    except db.Error as e:
        if getattr(e, "errno", None) == 1146:
            print("The user_account table does not exist yet. Run sql/07_add_user_accounts.sql in MySQL Workbench first.")
        else:
            print(f"MySQL error {getattr(e, 'errno', '')}: {getattr(e, 'msg', e)}")
        sys.exit(1)

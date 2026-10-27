"""Login, sessions, CSRF protection and role checks for CampusHub.

Security choices (see README, "Login and roles"):
  * passwords are stored only as salted, slow hashes (Werkzeug's scrypt) - never in plain text
  * after a successful login the old session is discarded (prevents session fixation)
  * the session remembers a fingerprint of the password hash, so changing or resetting a
    password signs the account out everywhere else
  * 5 wrong passwords lock the account for 15 minutes; an unknown login takes the same time
    as a wrong password, so the login page doesn't reveal which accounts exist
  * every POST form carries a per-session CSRF token
  * access is deny-by-default: app.py lists which endpoints students and faculty may open,
    everything else is admin-only; record-level checks stop people opening others' bookings
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from flask import abort, g, request, session
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

import queries as Q

ROLES = ("STUDENT", "FACULTY", "ADMIN")
ROLE_LABELS = {"STUDENT": "Student", "FACULTY": "Faculty", "ADMIN": "Administrator"}
MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_LENGTH, MAX_LENGTH = 8, 128

# A real hash of a random value: checking against it costs the same as a real check,
# so a login for an unknown e-mail is not answered faster than a wrong password.
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))


# ------------------------------------------------------------------ passwords
def hash_password(password):
    return generate_password_hash(password)          # salted scrypt (Werkzeug default)


def password_problems(password):
    """List of unmet rules (empty list = acceptable)."""
    problems = []
    if len(password) < MIN_LENGTH:
        problems.append(f"at least {MIN_LENGTH} characters")
    if len(password) > MAX_LENGTH:
        problems.append(f"at most {MAX_LENGTH} characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        problems.append("both letters and numbers")
    return problems


def temporary_password():
    """Random 12-character password without look-alike characters (0/O, 1/l/I)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(12))
        if not password_problems(pw):
            return pw


def _fingerprint(password_hash):
    return hashlib.sha256(password_hash.encode()).hexdigest()[:24]


# ------------------------------------------------------------------ login / logout
def authenticate(role, login, password, now=None):
    """Check a login attempt. Returns (account, None) or (None, message for the user)."""
    now = now or datetime.now()
    wrong = "The login or password is incorrect."
    login = (login or "").strip()
    if role not in ROLES or not login or not password or len(password) > MAX_LENGTH:
        check_password_hash(_DUMMY_HASH, password or "x")
        return None, wrong
    acc = Q.find_account(role, login)
    if acc is None:
        check_password_hash(_DUMMY_HASH, password)
        return None, wrong
    locked_until = as_datetime(acc["locked_until"])
    if locked_until and locked_until > now:
        return None, (f"Too many wrong passwords. This account is locked until {locked_until:%H:%M}. "
                      "Try again later or ask an administrator to unlock it.")
    if not check_password_hash(acc["password_hash"], password):
        Q.record_failed_login(acc["account_id"], MAX_FAILED, now + timedelta(minutes=LOCK_MINUTES))
        return None, wrong
    if not acc["is_active"]:
        return None, "This account has been disabled. Please contact the lab administrator."
    Q.record_successful_login(acc["account_id"], now)
    return acc, None


def start_session(acc):
    session.clear()                                   # new session id: prevents session fixation
    session.permanent = True
    session["account_id"] = acc["account_id"]
    session["fp"] = _fingerprint(acc["password_hash"])
    session["csrf"] = secrets.token_urlsafe(32)


def refresh_fingerprint(password_hash):
    """Keep the current session valid after the user changes their own password."""
    session["fp"] = _fingerprint(password_hash)


def end_session():
    session.clear()


def load_current_user():
    """Called before every request: sets g.user (or None)."""
    g.user = None
    account_id = session.get("account_id")
    if not account_id:
        return
    acc = Q.get_account(account_id)
    if (acc is None or not acc["is_active"]
            or not hmac.compare_digest(session.get("fp", ""), _fingerprint(acc["password_hash"]))):
        session.clear()                               # disabled, deleted or password changed elsewhere
        return
    acc = dict(acc)
    acc.pop("password_hash", None)                    # never keep the hash around in templates
    g.user = acc


# ------------------------------------------------------------------ roles and ownership
def role():
    return g.user["role"] if getattr(g, "user", None) else None


def is_admin():
    return role() == "ADMIN"


def owner():
    """(student_id, faculty_id) of the signed-in student / faculty member; None for admins."""
    u = getattr(g, "user", None)
    if not u or u["role"] == "ADMIN":
        return None
    return (u["student_id"], u["faculty_id"]) if u["role"] == "STUDENT" else (None, u["faculty_id"])


def owns(row):
    """True if a booking / issue row belongs to the signed-in person (admins own everything)."""
    if is_admin():
        return True
    u = getattr(g, "user", None)
    if not u:
        return False
    if u["role"] == "STUDENT":
        return row.get("student_id") is not None and row.get("student_id") == u["student_id"]
    return row.get("faculty_id") is not None and row.get("faculty_id") == u["faculty_id"]


def require_admin():
    if not is_admin():
        abort(403)


# ------------------------------------------------------------------ CSRF
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_field():
    return Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token()}">')


def check_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    if not sent or not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="csrf")


# ------------------------------------------------------------------ helpers
def as_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None

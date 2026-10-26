"""Template filters and helpers shared by every page."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import request, url_for
from markupsafe import Markup, escape

STATUS_LABELS = {
    "AVAILABLE": ("Available", "success"), "UNDER_MAINTENANCE": ("Under maintenance", "warning"),
    "INACTIVE": ("Inactive", "neutral"), "CONFIRMED": ("Confirmed", "info"), "COMPLETED": ("Completed", "success"),
    "CANCELLED": ("Cancelled", "neutral"), "ISSUED": ("Issued", "info"), "RETURNED": ("Returned", "success"),
    "OVERDUE": ("Overdue", "danger"), "ON TIME": ("On time", "success"), "ALL_ISSUED": ("All issued", "danger"),
    "UNDER_REPAIR": ("Under repair", "warning"), "REPORTED": ("Reported", "warning"),
    "IN_PROGRESS": ("In progress", "info"), "LOW": ("Low stock", "warning"), "OUT": ("Out of stock", "danger"),
    "FACILITY_ADMIN": ("Facility admin", "neutral"), "DEPARTMENT_ADMIN": ("Department admin", "neutral"),
    "SUPER_ADMIN": ("Super admin", "neutral"),
}


def to_minutes(value):
    """MySQL TIME columns arrive as timedelta; forms send 'HH:MM'."""
    if value is None:
        return None
    if isinstance(value, timedelta):
        return int(value.total_seconds()) // 60
    s = str(value)
    h, m = s.split(":")[:2]
    return int(h) * 60 + int(m)


def hm(value):
    mins = to_minutes(value)
    return "" if mins is None else f"{mins // 60:02d}:{mins % 60:02d}"


def as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def fmt_date(value, fmt="%d %b %Y"):
    d = as_date(value)
    return d.strftime(fmt) if d else ""


def fmt_datetime(value):
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.strftime("%d %b %Y, %H:%M")


def rel_day(value, today=None):
    d = as_date(value)
    if not d:
        return ""
    today = today or date.today()
    diff = (d - today).days
    if diff == 0:
        return "Today"
    if diff == 1:
        return "Tomorrow"
    if diff == -1:
        return "Yesterday"
    if 1 < diff < 7:
        return d.strftime("%A")
    return f"in {diff} days" if diff > 0 else f"{-diff} days ago"


def ref(booking_id):
    return f"BK-{int(booking_id):06d}"


def num(value, digits=0):
    if value is None:
        return "0"
    v = float(value) if isinstance(value, (Decimal, int, float)) else float(value or 0)
    return f"{v:,.{digits}f}"


def duration(start, end):
    a, b = to_minutes(start), to_minutes(end)
    if a is None or b is None:
        return ""
    mins = b - a
    h, m = divmod(mins, 60)
    return f"{h} h {m} min" if h and m else (f"{h} h" if h else f"{m} min")


def badge(status, text=None):
    label, tone = STATUS_LABELS.get(str(status), (str(status).replace("_", " ").title(), "neutral"))
    return Markup(f'<span class="badge-soft tone-{tone}">{escape(text or label)}</span>')


def stock_state(available, total):
    available, total = int(available or 0), int(total or 0)
    if available == 0:
        return "OUT"
    if total and available * 4 <= total:
        return "LOW"
    return "OK"


def url_with(**changes):
    """Current URL with some query arguments replaced (None removes one)."""
    args = request.args.to_dict()
    for k, v in changes.items():
        if v is None or v == "":
            args.pop(k, None)
        else:
            args[k] = v
    return url_for(request.endpoint, **(request.view_args or {}), **args)


def register(app):
    app.add_template_filter(hm)
    app.add_template_filter(fmt_date, "date")
    app.add_template_filter(fmt_datetime, "datetime")
    app.add_template_filter(rel_day)
    app.add_template_filter(ref)
    app.add_template_filter(num)
    app.add_template_filter(badge)
    app.add_template_global(duration)
    app.add_template_global(badge, "status_badge")
    app.add_template_global(stock_state)
    app.add_template_global(url_with)
    app.add_template_global(to_minutes)
    app.add_template_global(icon)


# Inline SVG icons (stroke style, 24x24) - no icon font or CDN needed
ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="1.5"/><path d="M9 21v-4h6v4"/>'
                '<path d="M8 7h2M14 7h2M8 11h2M14 11h2"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16.5" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    "calendar-check": '<rect x="3" y="4.5" width="18" height="16.5" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>'
                      '<path d="m9 15 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "box": '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 '
              '6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "chart": '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/>'
             '<path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.3c2 .8 3.5 2.8 3.5 5.7"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.6-3.6"/>',
    "bell": '<path d="M6 9a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
             '<path d="M12 9v4M12 17h.01"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="m8 12.5 3 3 5-6"/>',
    "x-circle": '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "activity": '<path d="M22 12h-4l-3 8L9 4l-3 8H2"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>'
                '<path d="M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "play": '<circle cx="12" cy="12" r="9"/><path d="m10 8.5 5.5 3.5-5.5 3.5z"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "list": '<path d="M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    "grid": '<path d="M3 9h18M3 15h18M9 3v18M15 3v18"/><rect x="3" y="3" width="18" height="18" rx="2"/>',
    "layers": '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
    "shield": '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6z"/><path d="m9 12 2 2 4-4"/>',
    "power": '<path d="M12 3v8"/><path d="M6.4 6.6a8 8 0 1 0 11.2 0"/>',
    "map-pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/>',
}


def icon(name, size=18, cls=""):
    body = ICONS.get(name, ICONS["info"])
    return Markup(f'<svg class="icon {cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
                  f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
                  f'aria-hidden="true">{body}</svg>')

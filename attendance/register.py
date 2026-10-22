import calendar
from datetime import date, timedelta

from .db import open_db


def add_maid(conn, name, monthly_salary, paid_leaves_per_month=2):
    cur = conn.execute(
        "INSERT INTO maid (name, monthly_salary, paid_leaves_per_month) VALUES (?, ?, ?)",
        (name, monthly_salary, paid_leaves_per_month),
    )
    return cur.lastrowid


def update_maid(conn, name, monthly_salary=None, paid_leaves_per_month=None, active=None):
    for column, value in (
        ("monthly_salary", monthly_salary),
        ("paid_leaves_per_month", paid_leaves_per_month),
        ("active", active),
    ):
        if value is not None:
            conn.execute(f"UPDATE maid SET {column} = ? WHERE name = ?", (value, name))


def list_maids(conn, active_only=True):
    sql = "SELECT * FROM maid" + (" WHERE active = 1" if active_only else "") + " ORDER BY name"
    return conn.execute(sql).fetchall()


def add_alias(conn, name, alias):
    conn.execute("INSERT OR IGNORE INTO maid_alias (maid_id, alias) VALUES (?, ?)",
                 (_maid_id(conn, name), alias.strip()))


def list_aliases(conn):
    """{maid name: [alias, ...]}"""
    out = {}
    for r in conn.execute("SELECT m.name, a.alias FROM maid_alias a JOIN maid m ON m.id = a.maid_id"):
        out.setdefault(r["name"], []).append(r["alias"])
    return out


def _maid_id(conn, name):
    row = conn.execute("SELECT id FROM maid WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise KeyError(f"unknown maid: {name}")
    return row["id"]


def mark(conn, name, day, status, source="manual", note=""):
    """Record a day. A leave entry is never overwritten by an automatic 'present'."""
    maid_id = _maid_id(conn, name)
    day = day.isoformat() if isinstance(day, date) else day
    existing = conn.execute(
        "SELECT status FROM attendance WHERE maid_id = ? AND day = ?", (maid_id, day)
    ).fetchone()
    if existing and existing["status"] == "leave" and status == "present" and source != "manual":
        return False
    conn.execute(
        "INSERT INTO attendance (maid_id, day, status, source, note) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(maid_id, day) DO UPDATE SET status = excluded.status, "
        "source = excluded.source, note = excluded.note",
        (maid_id, day, status, source, note),
    )
    return True


def mark_leave_range(conn, name, start, end, source="manual", note=""):
    day = start
    while day <= end:
        mark(conn, name, day, "leave", source, note)
        day += timedelta(days=1)


def month_summary(conn, year, month, today=None):
    """Per-maid leave summary. Days with no entry are 'unconfirmed', never auto-deducted."""
    days_in_month = calendar.monthrange(year, month)[1]
    today = today or date.today()
    if (year, month) < (today.year, today.month):
        counted_days = days_in_month
    elif (year, month) == (today.year, today.month):
        counted_days = today.day
    else:
        counted_days = 0
    prefix = f"{year:04d}-{month:02d}-"
    rows = []
    for maid in list_maids(conn):
        entries = conn.execute(
            "SELECT day, status FROM attendance WHERE maid_id = ? AND day LIKE ?",
            (maid["id"], prefix + "%"),
        ).fetchall()
        recorded = {e["day"]: e["status"] for e in entries}
        leave_days = sum(1 for s in recorded.values() if s == "leave")
        present_days = sum(1 for s in recorded.values() if s == "present")
        voice_days = sorted(e["day"] for e in conn.execute(
            "SELECT day FROM attendance WHERE maid_id = ? AND day LIKE ? "
            "AND status = 'leave' AND source = 'voice'", (maid["id"], prefix + "%")))
        unconfirmed = [d for d in range(1, counted_days + 1) if f"{prefix}{d:02d}" not in recorded]
        paid = min(leave_days, maid["paid_leaves_per_month"])
        unpaid = leave_days - paid
        deduction = round(maid["monthly_salary"] / days_in_month * unpaid, 2)
        rows.append({
            "name": maid["name"],
            "present_days": present_days,
            "leave_days": leave_days,
            "paid_leaves_allowed": maid["paid_leaves_per_month"],
            "paid_leave_days": paid,
            "unpaid_leave_days": unpaid,
            "voice_leave_days": voice_days,
            "unconfirmed_days": [f"{prefix}{d:02d}" for d in unconfirmed],
            "monthly_salary": maid["monthly_salary"],
            "deduction": deduction,
            "net_salary": round(maid["monthly_salary"] - deduction, 2),
        })
    return rows


def format_summary(rows, year, month):
    lines = [f"Leave summary for {calendar.month_name[month]} {year}", ""]
    for r in rows:
        lines.append(
            f"{r['name']}: {r['leave_days']} leave day(s) "
            f"({r['paid_leave_days']} paid of {r['paid_leaves_allowed']}, {r['unpaid_leave_days']} unpaid), "
            f"{r['present_days']} present. Deduction {r['deduction']:.2f}, net {r['net_salary']:.2f}."
        )
        if r["voice_leave_days"]:
            lines.append("  Logged by voice, please check: " + ", ".join(r["voice_leave_days"]))
        if r["unconfirmed_days"]:
            lines.append(f"  {len(r['unconfirmed_days'])} day(s) with no record, please confirm.")
    return "\n".join(lines)

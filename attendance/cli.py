import argparse
from datetime import date

from . import camera, register, web
from .db import open_db


def main(argv=None):
    p = argparse.ArgumentParser(prog="attendance")
    p.add_argument("--db", default="attendance.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add-maid")
    a.add_argument("name")
    a.add_argument("salary", type=float)
    a.add_argument("--paid-leaves", type=int, default=2)

    m = sub.add_parser("mark")
    m.add_argument("name")
    m.add_argument("status", choices=["present", "leave"])
    m.add_argument("--day", type=date.fromisoformat, default=date.today())
    m.add_argument("--until", type=date.fromisoformat, help="last day, for a leave range")

    s = sub.add_parser("summary")
    s.add_argument("--year", type=int, default=date.today().year)
    s.add_argument("--month", type=int, default=date.today().month)

    w = sub.add_parser("serve")
    w.add_argument("--port", type=int, default=8080)

    c = sub.add_parser("snapshot", help="save a still frame from a Home Assistant camera entity")
    c.add_argument("--entity", default="camera.doorcam_main")
    c.add_argument("--out", default="snapshot.jpg")

    args = p.parse_args(argv)
    if args.cmd == "serve":
        web.serve(args.db, port=args.port)
        return
    if args.cmd == "snapshot":
        path = camera.save_snapshot(args.entity, args.out)
        print(f"saved {path}")
        return
    with open_db(args.db) as conn:
        if args.cmd == "add-maid":
            register.add_maid(conn, args.name, args.salary, args.paid_leaves)
        elif args.cmd == "mark":
            register.mark_leave_range(conn, args.name, args.day, args.until or args.day) \
                if args.status == "leave" else register.mark(conn, args.name, args.day, "present")
        elif args.cmd == "summary":
            rows = register.month_summary(conn, args.year, args.month)
            print(register.format_summary(rows, args.year, args.month))


if __name__ == "__main__":
    main()

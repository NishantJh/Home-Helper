import argparse
import os
from datetime import date

from . import camera, faces, register, watch, web
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
    w.add_argument("--host", default="0.0.0.0")
    w.add_argument("--password", default=os.environ.get("ATTENDANCE_WEB_PASSWORD"),
                    help="required unless --host is 127.0.0.1/localhost; "
                         "also read from ATTENDANCE_WEB_PASSWORD")

    c = sub.add_parser("snapshot", help="save a still frame from a Home Assistant camera entity")
    c.add_argument("--entity", default="camera.doorcam_main")
    c.add_argument("--out", default="snapshot.jpg")

    f = sub.add_parser("train-faces", help="build a face-matching model from enrollment photos")
    f.add_argument("--faces-dir", default="faces", help="one subfolder of photos per maid")
    f.add_argument("--model", default="faces.xml")
    f.add_argument("--labels", default="faces_labels.json")

    v = sub.add_parser("watch", help="save a snapshot whenever a motion sensor reports a person")
    v.add_argument("--motion-entity", default="binary_sensor.doorcam_smart_motion_human")
    v.add_argument("--camera-entity", default="camera.doorcam_main")
    v.add_argument("--maid", help="unused without --faces-model: a hit is only marked present "
                                  "once a trained face match confirms who it is")
    v.add_argument("--out-dir", default="snapshots")
    v.add_argument("--poll-seconds", type=int, default=3)
    v.add_argument("--cooldown-seconds", type=int, default=90)
    v.add_argument("--keep-days", type=int, default=3, help="delete snapshots older than this")
    v.add_argument("--faces-model", help="trained model from train-faces, enables auto-recognition")
    v.add_argument("--faces-labels", help="labels file from train-faces")
    v.add_argument("--confidence-threshold", type=float, default=70)

    args = p.parse_args(argv)
    if args.cmd == "serve":
        web.serve(args.db, host=args.host, port=args.port, password=args.password)
        return
    if args.cmd == "snapshot":
        path = camera.save_snapshot(args.entity, args.out)
        print(f"saved {path}")
        return
    if args.cmd == "train-faces":
        result = faces.train(args.faces_dir, args.model, args.labels)
        print(f"trained on {result['trained']} photo(s) for {result['people']} maid(s)")
        if result["skipped"]:
            print(f"no face found, skipped: {', '.join(result['skipped'])}")
        return
    if args.cmd == "watch":
        print(f"watching {args.motion_entity}, polling every {args.poll_seconds}s (Ctrl+C to stop)")
        for path, recognized in watch.watch_motion(
            args.motion_entity, args.camera_entity, db_path=args.db, maid=args.maid,
            out_dir=args.out_dir, poll_seconds=args.poll_seconds,
            cooldown_seconds=args.cooldown_seconds, keep_days=args.keep_days,
            faces_model=args.faces_model, faces_labels=args.faces_labels,
            confidence_threshold=args.confidence_threshold,
        ):
            who = recognized or ("unrecognized" if args.faces_model else "saved")
            print(f"motion detected, {who}: {path}")
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

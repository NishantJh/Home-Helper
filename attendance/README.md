# Attendance register

Logs daily attendance and leave for domestic helpers, and produces a month-end leave summary with salary deductions. Standard library only.

    python3 -m attendance add-maid Sunita 12000 --paid-leaves 2
    python3 -m attendance mark Sunita leave --day 2026-10-05 --until 2026-10-07
    python3 -m attendance summary --year 2026 --month 10
    python3 -m attendance serve --port 8080      # web page to view and correct entries
    python3 -m attendance snapshot --entity camera.doorcam_main --out snapshot.jpg

Deduction = monthly salary / days in month x unpaid leave days. A day with no record is listed as unconfirmed and is never deducted automatically. An automatic "present" (camera or voice, added later) never overwrites a leave entry.

## Camera

Frames come from a camera already added to Home Assistant (e.g. via a Dahua/CP Plus HACS integration), fetched through HA's own `camera_proxy` REST endpoint -- the camera's RTSP username/password never needs to be stored in this project, only a Home Assistant long-lived access token. Set before running `snapshot` or the (planned) face check-in:

    HA_URL=http://homeassistant.local:8123
    HA_TOKEN=<long-lived access token from your HA profile page>

Run tests: `python3 -m unittest discover -s attendance/tests -t .`

Planned next: camera face check-in (match a snapshot against known maids), voice check-in and spoken leave commands, month-end Telegram/email report.

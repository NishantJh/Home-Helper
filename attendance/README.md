# Attendance register

Logs daily attendance and leave for domestic helpers, and produces a month-end leave summary with salary deductions. Standard library only.

    python3 -m attendance add-maid Sunita 12000 --paid-leaves 2
    python3 -m attendance mark Sunita leave --day 2026-10-05 --until 2026-10-07
    python3 -m attendance summary --year 2026 --month 10
    python3 -m attendance serve --port 8080      # web page to view and correct entries

Deduction = monthly salary / days in month x unpaid leave days. A day with no record is listed as unconfirmed and is never deducted automatically. An automatic "present" (camera or voice, added later) never overwrites a leave entry.

Run tests: `python3 -m unittest discover -s attendance/tests -t .`

Planned next: camera face check-in, voice check-in and spoken leave commands, month-end Telegram/email report.

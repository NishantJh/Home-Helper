# Attendance register

Logs daily attendance and leave for domestic helpers, and produces a month-end leave summary with salary deductions. Standard library only, except face recognition (see below).

    python3 -m attendance add-maid Sunita 12000 --paid-leaves 2
    python3 -m attendance mark Sunita leave --day 2026-10-05 --until 2026-10-07
    python3 -m attendance summary --year 2026 --month 10
    python3 -m attendance serve --port 8080      # web page to view and correct entries (see Web page below)
    python3 -m attendance snapshot --entity camera.doorcam_main --out snapshot.jpg
    python3 -m attendance train-faces --faces-dir faces   # build a face model from enrollment photos
    python3 -m attendance watch --faces-model faces.xml --faces-labels faces_labels.json

Deduction = monthly salary / days in month x unpaid leave days. A day with no record is listed as unconfirmed and is never deducted automatically. An automatic "present" (camera or voice, added later) never overwrites a logged leave; a correction made through the web page is a deliberate human edit and is allowed to.

## Web page

Requires a password: set `ATTENDANCE_WEB_PASSWORD`, or pass `--password`. Without one, `serve` refuses to start on anything but `127.0.0.1`/`localhost` (where it generates and prints a one-off password instead) -- otherwise anyone on the home Wi-Fi, or any site opened in a home browser, could see salaries and post corrections. The page uses HTTP Basic Auth and rejects any POST whose `Origin` doesn't match the server's own host.

## Camera

Frames come from a camera already added to Home Assistant (e.g. via a Dahua/CP Plus HACS integration), fetched through HA's own `camera_proxy` REST endpoint -- the camera's RTSP username/password never needs to be stored in this project, only a Home Assistant long-lived access token. Set before running `snapshot` or `watch`:

    HA_URL=http://homeassistant.local:8123
    HA_TOKEN=<long-lived access token from your HA profile page>

`watch` polls a motion binary_sensor (default `binary_sensor.doorcam_smart_motion_human`, which only fires for a person rather than any movement) instead of pulling frames on a timer, and saves a snapshot on every off->on transition, skipping transitions inside a cooldown window (default 90s, `--cooldown-seconds`) so one visit doesn't produce a run of near-duplicate snapshots. A hit is only ever marked present once a trained face model recognizes who it is -- without a model (or when nobody is recognized), the snapshot is just saved with no register entry, since marking *anyone* at the door present (a delivery, a guest) would mask a day the maid was actually absent; a day with no entry is already flagged as unconfirmed for review. Snapshots are deleted after `--keep-days` (default 3) since they're personal data, not just of the maids but of whoever else triggers the motion sensor. A camera or recognition error on one poll is logged and skipped rather than ending the whole watch.

## Face recognition

Needs `pip install -r attendance/requirements.txt` (OpenCV + numpy; everything else is standard library).

1. Collect 3-5 clear photos per maid under a faces folder, one subfolder per person:

       faces/Sunita/1.jpg
       faces/Sunita/2.jpg
       faces/Radha/1.jpg

2. Build the model: `python3 -m attendance train-faces --faces-dir faces --model faces.xml --labels faces_labels.json`. Photos with no detected face are skipped and listed, not silently dropped.
3. Run `watch --faces-model faces.xml --faces-labels faces_labels.json`. On each motion event it matches the snapshot against the trained model and marks whoever it recognizes present; a face it doesn't recognize confidently enough is never guessed at and marks nobody (`--confidence-threshold`, default 70, lower numbers mean a closer match in OpenCV's LBPH -- lower the threshold if it's matching the wrong person, raise it if it's missing real matches).

Enrollment photos, snapshots, and the trained model/labels files are personal/biometric data and are gitignored (`faces/`, `snapshots/`, `faces*.xml`, `faces*.json`) -- never commit them.

The face detector's cascade file is vendored in this package (`attendance/haarcascade_frontalface_default.xml`) rather than read from the OpenCV install, since some OpenCV wheel builds ship no cascade data files at all.

Run tests: `python3 -m unittest discover -s attendance/tests -t .`

Planned next: voice check-in and spoken leave commands, month-end Telegram/email report.

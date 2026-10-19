"""Grab a snapshot when a Home Assistant motion sensor fires, instead of
pulling frames from the camera on a fixed timer.

Polls a binary_sensor (e.g. the camera's "smart motion human" detector,
which only fires on a person rather than any movement) and saves a frame
on every off->on transition, skipping transitions inside a cooldown window
so one visit doesn't produce a run of near-duplicate snapshots.

A hit is only ever marked present when a trained face model recognizes who
it is. Without a model (or when nobody is recognized), the snapshot is
just saved, with no register entry -- a day with no entry is already
flagged as unconfirmed for review rather than silently counted either way
(see register.month_summary). Marking *anyone* at the door present, such
as a delivery visit, would otherwise mask a day the maid was actually
absent.

Snapshots are personal data (visitors, not just the maids), so they are
deleted after `keep_days` rather than kept forever.
"""
import glob
import os
import sys
import time
from datetime import datetime, timedelta

from . import camera, faces, register
from .db import open_db


def purge_old_snapshots(out_dir, keep_days, clock=datetime.now):
    cutoff = clock().timestamp() - keep_days * 86400
    for path in glob.glob(os.path.join(out_dir, "*.jpg")):
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass  # already gone, or a permissions hiccup -- not fatal


def watch_motion(motion_entity, camera_entity, db_path=None, maid=None,
                  out_dir="snapshots", poll_seconds=3, cooldown_seconds=90,
                  keep_days=3, faces_model=None, faces_labels=None,
                  confidence_threshold=70, ha_url=None, token=None,
                  sleep=time.sleep, clock=datetime.now, log=lambda msg: print(msg, file=sys.stderr)):
    """Generator: blocks polling `motion_entity`'s state. Yields
    (snapshot_path, recognized_name_or_None) on each off->on transition
    outside the cooldown, forever (stop by breaking out of the loop you
    drive it with, e.g. Ctrl+C from the CLI). A camera/recognition error on
    one poll is logged and skipped rather than ending the whole watch.
    """
    os.makedirs(out_dir, exist_ok=True)
    if maid and not faces_model:
        log(f"--maid {maid} has no effect without --faces-model: a camera hit is only "
            f"marked present once a trained face match confirms who it is, to avoid "
            f"marking the maid present just because someone (e.g. a delivery) was at the door.")
    cooldown = timedelta(seconds=cooldown_seconds)
    last_capture = None
    was_on = None
    while True:
        sleep(poll_seconds)
        try:
            is_on = camera.get_state(motion_entity, ha_url, token) == "on"
        except camera.CameraError as e:
            log(f"could not read {motion_entity}: {e}")
            continue
        now = clock()
        if was_on is None:
            was_on = is_on  # first poll: establish a baseline, don't treat it as a transition
            continue
        if is_on and not was_on and (last_capture is None or now - last_capture >= cooldown):
            last_capture = now
            out_path = os.path.join(
                out_dir, f"{camera_entity}-{now.strftime('%Y%m%dT%H%M%S')}.jpg"
            )
            try:
                camera.save_snapshot(camera_entity, out_path, ha_url, token)
                recognized = None
                if faces_model and faces_labels:
                    recognized, _ = faces.recognize(
                        out_path, faces_model, faces_labels, confidence_threshold
                    )
                if recognized and db_path:
                    with open_db(db_path) as conn:
                        register.mark(conn, recognized, now.date(), "present", source="camera")
            except (camera.CameraError, faces.FaceError, KeyError) as e:
                log(f"motion event at {now}: {e}")
                was_on = is_on
                continue
            purge_old_snapshots(out_dir, keep_days, clock)
            yield out_path, recognized
        was_on = is_on

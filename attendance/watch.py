"""Grab a snapshot when a Home Assistant motion sensor fires, instead of
pulling frames from the camera on a fixed timer.

Polls a binary_sensor (e.g. the camera's "smart motion human" detector,
which only fires on a person rather than any movement) and saves a frame
on every off->on transition, skipping transitions inside a cooldown window
so one visit doesn't produce a run of near-duplicate snapshots. With a
trained face model it also matches the snapshot against enrolled maids and
marks whoever it recognises present; with just --maid it marks that one
maid present on every event (useful before enrollment, or with one maid).
"""
import os
import time
from datetime import datetime, timedelta

from . import camera, faces, register
from .db import open_db


def watch_motion(motion_entity, camera_entity, db_path=None, maid=None,
                  out_dir="snapshots", poll_seconds=3, cooldown_seconds=90,
                  faces_model=None, faces_labels=None, confidence_threshold=70,
                  ha_url=None, token=None, sleep=time.sleep, clock=datetime.now):
    """Generator: blocks polling `motion_entity`'s state. Yields
    (snapshot_path, recognized_name_or_None) on each off->on transition
    outside the cooldown, forever (stop by breaking out of the loop you
    drive it with, e.g. Ctrl+C from the CLI).
    """
    os.makedirs(out_dir, exist_ok=True)
    was_on = camera.get_state(motion_entity, ha_url, token) == "on"
    cooldown = timedelta(seconds=cooldown_seconds)
    last_capture = None
    while True:
        sleep(poll_seconds)
        is_on = camera.get_state(motion_entity, ha_url, token) == "on"
        now = clock()
        if is_on and not was_on and (last_capture is None or now - last_capture >= cooldown):
            last_capture = now
            out_path = os.path.join(
                out_dir, f"{camera_entity}-{now.strftime('%Y%m%dT%H%M%S')}.jpg"
            )
            camera.save_snapshot(camera_entity, out_path, ha_url, token)
            recognized = None
            if faces_model and faces_labels:
                recognized, _ = faces.recognize(
                    out_path, faces_model, faces_labels, confidence_threshold
                )
                present_as = recognized  # don't guess who it was when matching failed
            else:
                present_as = maid  # no model configured: single-maid mode, as before
            if present_as and db_path:
                with open_db(db_path) as conn:
                    register.mark(conn, present_as, now.date(), "present", source="camera")
            yield out_path, recognized
        was_on = is_on

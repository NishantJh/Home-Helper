"""Grab a snapshot when a Home Assistant motion sensor fires, instead of
pulling frames from the camera on a fixed timer.

Polls a binary_sensor (e.g. the camera's "smart motion human" detector,
which only fires on a person rather than any movement) and saves a frame
on every off->on transition. Optionally marks a maid present at the same
time -- useful while there is exactly one maid and no face recognition yet
(see README "Planned next").
"""
import os
import time
from datetime import datetime

from . import camera, register
from .db import open_db


def watch_motion(motion_entity, camera_entity, db_path=None, maid=None,
                  out_dir="snapshots", poll_seconds=3, ha_url=None, token=None,
                  sleep=time.sleep, clock=datetime.now):
    """Generator: blocks polling `motion_entity`'s state. Yields the saved
    snapshot path on each off->on transition, forever (stop by breaking out
    of the loop you drive it with, e.g. Ctrl+C from the CLI).
    """
    os.makedirs(out_dir, exist_ok=True)
    was_on = camera.get_state(motion_entity, ha_url, token) == "on"
    while True:
        sleep(poll_seconds)
        is_on = camera.get_state(motion_entity, ha_url, token) == "on"
        if is_on and not was_on:
            now = clock()
            out_path = os.path.join(
                out_dir, f"{camera_entity}-{now.strftime('%Y%m%dT%H%M%S')}.jpg"
            )
            camera.save_snapshot(camera_entity, out_path, ha_url, token)
            if maid and db_path:
                with open_db(db_path) as conn:
                    register.mark(conn, maid, now.date(), "present", source="camera")
            yield out_path
        was_on = is_on

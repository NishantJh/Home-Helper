import itertools
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from attendance import register, watch
from attendance.db import connect, open_db


class WatchMotionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out_dir = os.path.join(self.tmp, "snapshots")
        self.db_path = os.path.join(self.tmp, "attendance.db")
        with open_db(self.db_path) as conn:
            register.add_maid(conn, "Sunita", 3000)

    def _run(self, states, max_events, maid=None, cooldown_seconds=0, clock=None,
             faces_model=None, faces_labels=None, keep_days=3):
        states_iter = iter(states)

        def fake_get_state(entity_id, ha_url=None, token=None):
            return next(states_iter)

        saved = []

        def fake_save_snapshot(entity_id, out_path, ha_url=None, token=None):
            saved.append(out_path)
            with open(out_path, "wb") as f:
                f.write(b"fake")
            return out_path

        with patch("attendance.camera.get_state", side_effect=fake_get_state), \
             patch("attendance.camera.save_snapshot", side_effect=fake_save_snapshot):
            gen = watch.watch_motion(
                "binary_sensor.doorcam_smart_motion_human", "camera.doorcam_main",
                db_path=self.db_path, maid=maid, out_dir=self.out_dir,
                poll_seconds=0, sleep=lambda s: None, cooldown_seconds=cooldown_seconds,
                keep_days=keep_days, faces_model=faces_model, faces_labels=faces_labels,
                clock=clock or (lambda: datetime(2026, 10, 19, 12, 0, 0)),
            )
            return list(itertools.islice(gen, max_events)), saved

    def test_snapshot_only_on_off_to_on_transition(self):
        # off, off->on (snap), stays on (no snap), on->off, off->on (snap)
        states = ["off", "off", "on", "on", "off", "on"]
        events, saved = self._run(states, max_events=2)
        self.assertEqual(len(events), 2)
        self.assertEqual(len(saved), 2)
        self.assertTrue(all(os.path.exists(p) for p in saved))

    def test_maid_without_a_face_model_does_not_auto_mark_present(self):
        # C1: anyone at the door (a delivery, a guest) would otherwise mark
        # the maid present, masking a day she was actually absent. A camera
        # hit without a face match just saves the snapshot.
        states = ["off", "off", "on"]
        events, saved = self._run(states, max_events=1, maid="Sunita")
        self.assertEqual(len(saved), 1)
        with open_db(self.db_path) as conn:
            row = register.month_summary(conn, 2026, 10, today=datetime(2026, 10, 19).date())[0]
        self.assertEqual(row["present_days"], 0)

    def test_already_on_at_start_does_not_immediately_snapshot(self):
        # sensor is already "on" when watching begins; that shouldn't itself
        # count as a transition -- only off->on firing *after* that should.
        states = ["on", "on", "off", "on"]
        events, saved = self._run(states, max_events=1)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(saved), 1)

    def test_cooldown_suppresses_a_transition_right_after_the_last_one(self):
        # off->on, off->on again a moment later (inside the cooldown, so it
        # shouldn't snapshot), then off->on once more after the cooldown.
        states = ["off", "off", "on", "off", "on", "off", "on"]
        ticks = iter([
            datetime(2026, 10, 19, 12, 0, 0),
            datetime(2026, 10, 19, 12, 0, 1),
            datetime(2026, 10, 19, 12, 0, 2),
            datetime(2026, 10, 19, 12, 0, 3),
            datetime(2026, 10, 19, 12, 0, 4),  # still inside a 90s cooldown
            datetime(2026, 10, 19, 12, 2, 0),
            datetime(2026, 10, 19, 12, 2, 1),  # 120s after the first capture
        ])
        events, saved = self._run(
            states, max_events=2, cooldown_seconds=90, clock=lambda: next(ticks),
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(len(saved), 2)

    def test_recognized_maid_is_marked_present_not_the_fallback_maid(self):
        with open_db(self.db_path) as conn:
            register.add_maid(conn, "Radha", 3000)
        states = ["off", "off", "on"]
        with patch("attendance.faces.recognize", return_value=("Radha", 20)):
            self._run(
                states, max_events=1, maid="Sunita",
                faces_model="model.xml", faces_labels="labels.json",
            )
        with open_db(self.db_path) as conn:
            rows = {r["name"]: r for r in register.month_summary(
                conn, 2026, 10, today=datetime(2026, 10, 19).date()
            )}
        self.assertEqual(rows["Radha"]["present_days"], 1)
        self.assertEqual(rows["Sunita"]["present_days"], 0)

    def test_unrecognized_face_is_not_marked_as_the_fallback_maid(self):
        states = ["off", "off", "on"]
        with patch("attendance.faces.recognize", return_value=(None, 95)):
            self._run(
                states, max_events=1, maid="Sunita",
                faces_model="model.xml", faces_labels="labels.json",
            )
        with open_db(self.db_path) as conn:
            row = register.month_summary(conn, 2026, 10, today=datetime(2026, 10, 19).date())[0]
        self.assertEqual(row["present_days"], 0)


    def test_a_camera_error_is_logged_and_the_watch_keeps_going(self):
        # C3: Home Assistant being briefly unreachable shouldn't kill the
        # whole watch process.
        states_iter = iter(["off", camera_error(), "off", "on"])

        def fake_get_state(entity_id, ha_url=None, token=None):
            value = next(states_iter)
            if isinstance(value, Exception):
                raise value
            return value

        logged = []
        with patch("attendance.camera.get_state", side_effect=fake_get_state), \
             patch("attendance.camera.save_snapshot", side_effect=lambda *a, **k: open(a[1], "wb").close()):
            gen = watch.watch_motion(
                "binary_sensor.doorcam_smart_motion_human", "camera.doorcam_main",
                db_path=self.db_path, out_dir=self.out_dir, poll_seconds=0,
                sleep=lambda s: None, cooldown_seconds=0,
                clock=lambda: datetime(2026, 10, 19, 12, 0, 0), log=logged.append,
            )
            events = list(itertools.islice(gen, 1))
        self.assertEqual(len(events), 1)
        self.assertTrue(any("could not read" in msg for msg in logged))

    def test_old_snapshots_are_purged_after_a_new_one_is_saved(self):
        os.makedirs(self.out_dir, exist_ok=True)
        stale = os.path.join(self.out_dir, "old.jpg")
        with open(stale, "wb") as f:
            f.write(b"old")
        old_time = (datetime(2026, 10, 19) - timedelta(days=10)).timestamp()
        os.utime(stale, (old_time, old_time))

        states = ["off", "off", "on"]
        self._run(states, max_events=1, keep_days=3)
        self.assertFalse(os.path.exists(stale))


def camera_error():
    from attendance.camera import CameraError

    return CameraError("could not reach Home Assistant")


if __name__ == "__main__":
    unittest.main()

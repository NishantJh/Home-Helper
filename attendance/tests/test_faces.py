import json
import os
import tempfile
import unittest

import numpy as np

from attendance import faces


def _pattern(seed, size=faces.FACE_SIZE):
    """A deterministic synthetic 'face' so training/matching can be tested
    without real photos -- LBPH works on any grayscale image, it doesn't
    care that these aren't faces, so this exercises the real train/predict
    path without needing a face detector or test photos."""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, size=size, dtype=np.uint8)


class FacesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.model_path = os.path.join(self.tmp, "model.xml")
        self.labels_path = os.path.join(self.tmp, "labels.json")

    def _train_with_patterns(self):
        # Bypass real image I/O: build the training set directly instead of
        # going through faces.train's directory walk, since our "photos"
        # are synthetic arrays, not real files OpenCV can decode.
        import cv2

        samples, labels, names = [], [], ["Sunita", "Radha"]
        for label_id, (name, seed) in enumerate((("Sunita", 1), ("Radha", 2))):
            for i in range(3):
                samples.append(_pattern(seed * 10 + i))
                labels.append(label_id)
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(samples, np.array(labels))
        recognizer.write(self.model_path)
        with open(self.labels_path, "w") as f:
            json.dump({i: n for i, n in enumerate(names)}, f)

    def test_recognize_matches_enrolled_pattern(self):
        self._train_with_patterns()
        name, confidence = faces.recognize(
            "unused", self.model_path, self.labels_path,
            detector=lambda img: _pattern(10),  # Sunita's first sample, unchanged
        )
        self.assertEqual(name, "Sunita")
        self.assertEqual(confidence, 0.0)

    def test_recognize_no_face_detected(self):
        self._train_with_patterns()
        name, confidence = faces.recognize(
            "unused", self.model_path, self.labels_path, detector=lambda img: None,
        )
        self.assertIsNone(name)
        self.assertIsNone(confidence)

    def test_recognize_requires_trained_model(self):
        with self.assertRaises(faces.FaceError):
            faces.recognize("unused", "/no/such/model.xml", self.labels_path)

    def test_detect_face_on_blank_image_finds_nothing(self):
        blank = np.zeros((300, 300, 3), dtype=np.uint8)
        self.assertIsNone(faces.detect_face(blank))

    def test_train_reports_photos_with_no_detected_face(self):
        import cv2

        d = os.path.join(self.tmp, "flat")
        os.makedirs(os.path.join(d, "Sunita"))
        blank_path = os.path.join(d, "Sunita", "1.jpg")
        cv2.imwrite(blank_path, np.zeros((300, 300, 3), dtype=np.uint8))
        with self.assertRaises(faces.FaceError):
            faces.train(d, os.path.join(self.tmp, "m2.xml"), os.path.join(self.tmp, "l2.json"))


if __name__ == "__main__":
    unittest.main()

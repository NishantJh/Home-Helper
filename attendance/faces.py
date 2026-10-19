"""Face enrollment and matching for camera check-in, built on OpenCV.

Enrollment layout: a few photos per maid under a faces directory --
    faces/Sunita/1.jpg
    faces/Sunita/2.jpg
    faces/Radha/1.jpg
`train()` builds a small LBPH model from these; `recognize()` matches a
camera snapshot against it. Nothing here calls out to a network or stores
anything beyond the model file and a name-per-label map, both local.
"""
import json
import os

import cv2
import numpy as np

FACE_SIZE = (200, 200)
# Vendored here rather than read from cv2.data.haarcascades: some OpenCV
# wheel builds (including the one this was developed against) ship no
# cascade data files at all, so relying on the install would break
# face detection unpredictably depending on how OpenCV got installed.
_CASCADE_PATH = os.path.join(os.path.dirname(__file__), "haarcascade_frontalface_default.xml")


class FaceError(Exception):
    pass


def _cascade():
    clf = cv2.CascadeClassifier(_CASCADE_PATH)
    if clf.empty():
        raise FaceError(f"could not load face detector from {_CASCADE_PATH}")
    return clf


def detect_face(image_bgr):
    """Return the largest detected face as a resized grayscale array, or None."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    faces = _cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return cv2.resize(gray[y:y + h, x:x + w], FACE_SIZE)


def _load_image(path_or_bytes):
    if isinstance(path_or_bytes, (bytes, bytearray)):
        arr = np.frombuffer(path_or_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    else:
        image = cv2.imread(path_or_bytes)
    if image is None:
        raise FaceError("could not read image")
    return image


def train(faces_dir, model_path, labels_path, detector=detect_face):
    """Build an LBPH model from faces_dir/<name>/*.jpg(.png). Skips photos
    with no detected face rather than failing the whole run, and reports
    them so a bad enrollment photo doesn't silently vanish."""
    names = sorted(
        n for n in os.listdir(faces_dir) if os.path.isdir(os.path.join(faces_dir, n))
    )
    if not names:
        raise FaceError(f"no per-maid subfolders found under {faces_dir}")
    label_names = {i: name for i, name in enumerate(names)}
    samples, labels, skipped = [], [], []
    for label_id, name in label_names.items():
        person_dir = os.path.join(faces_dir, name)
        photos = sorted(
            f for f in os.listdir(person_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )
        for photo in photos:
            path = os.path.join(person_dir, photo)
            face = detector(_load_image(path))
            if face is None:
                skipped.append(path)
                continue
            samples.append(face)
            labels.append(label_id)
    if not samples:
        raise FaceError("no usable face found in any enrollment photo")
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.train(samples, np.array(labels))
    recognizer.write(model_path)
    with open(labels_path, "w") as f:
        json.dump(label_names, f)
    return {"trained": len(samples), "people": len(names), "skipped": skipped}


def recognize(image, model_path, labels_path, confidence_threshold=70, detector=None):
    """Match a snapshot (file path or JPEG bytes) against a trained model.

    LBPH confidence is a distance, lower means a closer match, so a result
    is only returned when it's at or under confidence_threshold (around 70
    is a reasonable start; lower it if it's matching the wrong person,
    raise it if it's missing real matches). Returns (name, confidence) or
    (None, None) if no face was found or no match was close enough.
    """
    if not os.path.exists(model_path):
        raise FaceError(f"no trained model at {model_path}, run 'train-faces' first")
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(model_path)
    with open(labels_path) as f:
        label_names = {int(k): v for k, v in json.load(f).items()}
    if detector is None:
        face = detect_face(_load_image(image))
    else:
        face = detector(image)  # test seam: caller's detector handles `image` itself
    if face is None:
        return None, None
    label_id, confidence = recognizer.predict(face)
    if confidence > confidence_threshold:
        return None, confidence
    return label_names.get(label_id), confidence

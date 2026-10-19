"""Pull a still frame from a camera already set up in Home Assistant.

Goes through HA's camera_proxy REST endpoint instead of talking RTSP to the
camera directly, so the camera's own username/password never needs to live
in this codebase -- only a Home Assistant long-lived access token does.

Configure via environment variables (a .env file is not read; export them
in the shell or service unit that runs this):
    HA_URL    e.g. http://homeassistant.local:8123  (no trailing slash)
    HA_TOKEN  a long-lived access token from the HA user profile page
"""
import os
import urllib.request
from urllib.error import HTTPError, URLError


class CameraError(Exception):
    pass


def fetch_snapshot(entity_id, ha_url=None, token=None, timeout=10):
    """Return the current JPEG frame for a camera entity, as bytes."""
    ha_url = ha_url or os.environ.get("HA_URL")
    token = token or os.environ.get("HA_TOKEN")
    if not ha_url:
        raise CameraError("HA_URL is not set")
    if not token:
        raise CameraError("HA_TOKEN is not set")
    url = f"{ha_url.rstrip('/')}/api/camera_proxy/{entity_id}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as e:
        raise CameraError(f"Home Assistant returned {e.code} for {entity_id}") from e
    except URLError as e:
        raise CameraError(f"could not reach Home Assistant at {ha_url}: {e.reason}") from e


def save_snapshot(entity_id, out_path, ha_url=None, token=None):
    data = fetch_snapshot(entity_id, ha_url, token)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path

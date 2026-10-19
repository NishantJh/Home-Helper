import unittest
from unittest.mock import patch, MagicMock

from attendance import camera


class CameraTest(unittest.TestCase):
    def test_missing_url_raises(self):
        with self.assertRaises(camera.CameraError):
            camera.fetch_snapshot("camera.doorcam_main", ha_url=None, token="x")

    def test_missing_token_raises(self):
        with self.assertRaises(camera.CameraError):
            camera.fetch_snapshot("camera.doorcam_main", ha_url="http://ha.local:8123", token=None)

    @patch("attendance.camera.urllib.request.urlopen")
    def test_fetch_snapshot_hits_camera_proxy_with_auth(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"\xff\xd8fakejpeg"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        data = camera.fetch_snapshot(
            "camera.doorcam_main", ha_url="http://ha.local:8123/", token="secret"
        )

        self.assertEqual(data, b"\xff\xd8fakejpeg")
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "http://ha.local:8123/api/camera_proxy/camera.doorcam_main")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")


if __name__ == "__main__":
    unittest.main()

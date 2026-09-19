import json
import unittest
from urllib.parse import urlsplit

from runtime.voicebox_service import (
    VoiceboxClient,
    VoiceboxConfigurationError,
    VoiceboxGenerationError,
    VoiceboxConfig,
)


class FakeResponse:
    def __init__(self, payload, *, content_type="application/json"):
        self.payload = payload
        self.status = 200
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(payload)),
        }

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class VoiceboxOpener:
    def __init__(self):
        self.requests = []
        self.generation_status = "completed"

    def __call__(self, request, *, timeout):
        path = urlsplit(request.full_url).path
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        self.requests.append((request.method, path, dict(request.header_items()), body, timeout))
        if path == "/health":
            return self._json({"status": "healthy", "model_loaded": False})
        if path == "/profiles":
            return self._json([{"id": "profile-1", "name": "Synthetic Test Voice"}])
        if path == "/speak":
            return self._json({"id": "generation-1", "status": "generating", **body})
        if path == "/history/generation-1":
            return self._json(
                {
                    "id": "generation-1",
                    "status": self.generation_status,
                    "error": "synthetic failure" if self.generation_status == "failed" else None,
                }
            )
        if path == "/audio/generation-1":
            return FakeResponse(b"RIFFsynthetic-wave", content_type="audio/wav")
        raise AssertionError(f"unexpected test request: {request.method} {path}")

    def _json(self, payload):
        return FakeResponse(json.dumps(payload).encode("utf-8"))


class VoiceboxServiceTests(unittest.TestCase):
    def setUp(self):
        self.opener = VoiceboxOpener()
        self.config = VoiceboxConfig(
            enabled=True,
            base_url="http://127.0.0.1:17493",
            client_id="narratiive-tests",
            default_profile="Synthetic Test Voice",
            default_engine="qwen",
        )
        self.client = VoiceboxClient(self.config, opener=self.opener)

    def test_config_is_disabled_and_loopback_only_by_default(self):
        config = VoiceboxConfig.from_env({})
        self.assertFalse(config.enabled)
        with self.assertRaises(VoiceboxConfigurationError):
            VoiceboxConfig(enabled=True, base_url="http://voicebox.internal:17493")
        with self.assertRaises(VoiceboxConfigurationError):
            VoiceboxConfig(
                enabled=True,
                base_url="http://voicebox.internal:17493",
                allow_remote=True,
            )

    def test_remote_https_requires_explicit_opt_in(self):
        with self.assertRaises(VoiceboxConfigurationError):
            VoiceboxConfig(
                enabled=True,
                base_url="https://voicebox.internal",
                allow_remote=True,
            )
        config = VoiceboxConfig(
            enabled=True,
            base_url="https://voicebox.internal",
            allow_remote=True,
            bearer_token="synthetic-test-token",
        )
        self.assertTrue(config.allow_remote)

    def test_disabled_client_fails_closed(self):
        with self.assertRaises(VoiceboxConfigurationError):
            VoiceboxClient(VoiceboxConfig(), opener=self.opener).health()

    def test_health_and_profiles_use_client_identity(self):
        self.assertEqual(self.client.health()["status"], "healthy")
        self.assertEqual(self.client.list_profiles()[0]["name"], "Synthetic Test Voice")
        headers = self.opener.requests[0][2]
        self.assertEqual(headers["X-voicebox-client-id"], "narratiive-tests")

    def test_speak_uses_explicit_or_configured_defaults(self):
        result = self.client.speak("Synthetic message", language="en", personality=False)
        self.assertEqual(result["id"], "generation-1")
        body = self.opener.requests[-1][3]
        self.assertEqual(body["profile"], "Synthetic Test Voice")
        self.assertEqual(body["engine"], "qwen")
        self.assertEqual(body["personality"], False)

    def test_wait_and_download_completed_generation(self):
        generation = self.client.wait_for_generation("generation-1")
        self.assertEqual(generation["status"], "completed")
        self.assertEqual(self.client.download_audio("generation-1"), b"RIFFsynthetic-wave")

    def test_failed_generation_is_reported(self):
        self.opener.generation_status = "failed"
        with self.assertRaisesRegex(VoiceboxGenerationError, "synthetic failure"):
            self.client.wait_for_generation("generation-1")


if __name__ == "__main__":
    unittest.main()

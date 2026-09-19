from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.higgsfield_creative_production import (
    HiggsfieldConfig,
    HiggsfieldCreativeProductionDispatcher,
    HiggsfieldProviderError,
    higgsfield_credential,
)


class _Response:
    def __init__(self, payload, *, headers=None, raw=False):
        self.payload = payload
        self.headers = headers or {}
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _size=-1):
        return self.payload if self.raw else json.dumps(self.payload).encode()


class _Router:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


def _contract(capability="image_generation"):
    return {
        "workflow_context": {
            "workflow_id": "creative_bible_to_asset_production",
            "idempotency_key": "safe-run:execute:1",
        },
        "asset_manifest": {
            "assets": [{
                "asset_id": "safe-asset-1",
                "production_job_id": "safe-job-1",
                "specification_id": "safe-spec-1",
                "planned_version": 1,
            }]
        },
        "production_tasks": [{
            "job_id": "safe-job-1",
            "specification_id": "safe-spec-1",
            "required_capability": capability,
        }],
        "channel_asset_specifications": [{
            "specification_id": "safe-spec-1",
            "aspect_ratio": "1080:1920",
            "file_format": "png",
            "creative_direction": {
                "visual_direction": "A safe synthetic product image",
                "message": "Synthetic test only",
            },
        }],
    }


class HiggsfieldCreativeProductionTests(unittest.TestCase):
    def test_accepts_combined_or_separate_credentials(self):
        self.assertEqual(higgsfield_credential({"HF_KEY": "id:secret"}), "id:secret")
        self.assertEqual(
            higgsfield_credential({"HF_API_KEY_ID": "id", "HF_API_KEY_SECRET": "secret"}),
            "id:secret",
        )
        self.assertEqual(higgsfield_credential({"HF_API_KEY_ID": "id:secret"}), "id:secret")

    def test_generates_downloads_and_ingests_exact_asset_then_replays(self):
        router = _Router([
            _Response(
                {
                    "request_id": "request-1",
                    "status_url": "https://api.higgsfield.ai/requests/request-1/status",
                },
                headers={"X-Correlation-ID": "correlation-1"},
            ),
            _Response({"status": "completed", "images": [{"url": "https://cdn.example/image.png"}]}),
            _Response(b"safe synthetic png", headers={"Content-Type": "image/png"}, raw=True),
        ])
        drive_calls = []

        def drive(contract):
            drive_calls.append(contract)
            return {
                "verified": True,
                "file_id": "drive-1",
                "file_url": "https://drive.google.invalid/drive-1",
            }

        with tempfile.TemporaryDirectory() as temporary:
            dispatcher = HiggsfieldCreativeProductionDispatcher(
                HiggsfieldConfig("id:secret"),
                state_root=Path(temporary),
                drive_dispatcher=drive,
                opener=router,
                sleeper=lambda _seconds: None,
            )
            result = dispatcher(_contract())
            retry_contract = _contract()
            retry_contract["workflow_context"]["idempotency_key"] = "safe-run:execute:2"
            replay = dispatcher(retry_contract)

        self.assertEqual(len(router.requests), 3)
        submission = json.loads(router.requests[0].data)
        self.assertEqual(submission["aspect_ratio"], "9:16")
        self.assertEqual(result, replay)
        self.assertEqual(result["asset_versions"][0]["drive_uri"], "https://drive.google.invalid/drive-1")
        self.assertEqual(result["production_receipts"][0]["provider_request_id"], "request-1")
        self.assertFalse(result["publication_authorised"])
        self.assertEqual(len(drive_calls), 1)
        self.assertEqual(drive_calls[0]["payload"]["kind"], "creative_asset_version")

    def test_unsupported_capability_fails_before_provider_call(self):
        router = _Router([])
        with tempfile.TemporaryDirectory() as temporary:
            dispatcher = HiggsfieldCreativeProductionDispatcher(
                HiggsfieldConfig("id:secret"),
                state_root=Path(temporary),
                drive_dispatcher=lambda _contract: {},
                opener=router,
            )
            with self.assertRaisesRegex(HiggsfieldProviderError, "audio_production"):
                dispatcher(_contract("audio_production"))
        self.assertEqual(router.requests, [])


if __name__ == "__main__":
    unittest.main()

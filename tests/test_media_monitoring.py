from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.execution_journal import ExecutionJournal
from runtime.media_control import MediaControlError, MediaControlService, MediaProvider
from runtime.tony_media_commands import TonyMediaCommandService
from tests.test_media_control import _Fallback, adapter, identity, mapping, response


class MediaMonitoringTests(unittest.TestCase):
    def _service_with_history(self, directory: str) -> MediaControlService:
        provider = MediaProvider.META
        provider_adapter = adapter(provider)
        service = MediaControlService({provider: provider_adapter}, ExecutionJournal(directory))
        first = response(provider)
        first.update({"period_start": "2026-09-01T00:00:00Z", "period_end": "2026-09-08T00:00:00Z"})
        first["metrics"] = {**first["metrics"], "spend": "100", "impressions": "10000", "ctr": "1", "roas": "2"}
        provider_adapter.transport.responses["get_performance"] = first
        service.ingest(
            identity=identity(), provider_mapping=mapping(provider),
            period_start=first["period_start"], period_end=first["period_end"],
            request_id="monitor-first", tony_request="weekly media monitor",
        )
        second = response(provider)
        second.update({"period_start": "2026-09-08T00:00:00Z", "period_end": "2026-09-15T00:00:00Z"})
        second["metrics"] = {**second["metrics"], "spend": "180", "impressions": "12000", "ctr": "0.5", "roas": "0.8"}
        provider_adapter.transport.responses["get_performance"] = second
        service.ingest(
            identity=identity(), provider_mapping=mapping(provider),
            period_start=second["period_start"], period_end=second["period_end"],
            request_id="monitor-second", tony_request="weekly media monitor",
        )
        return service

    def test_report_separates_observations_signals_and_recommendations(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service_with_history(directory)
            report = service.monitor(
                cadence="weekly",
                query="northstar-test-co",
                generated_at="2026-09-29T08:00:00Z",
            )
            self.assertEqual(len(service.snapshot_history()), 2)
            self.assertEqual(len(service.snapshots()), 1)
            self.assertEqual(report["facts"][0]["classification"], "observed_fact")
            self.assertTrue(any(item["metric"] == "spend" and item["change_percent"] == "80.00" for item in report["trends"]))
            self.assertTrue(any(item["classification"] == "rule_based_signal" for item in report["exceptions"]))
            self.assertTrue(any(item["category"] == "provider_health" for item in report["exceptions"]))
            self.assertTrue(all(item["classification"] == "rule_based_interpretation" for item in report["recommendations"]))
            self.assertTrue(all(item["causal_claim"] is False for item in report["recommendations"]))
            self.assertFalse(report["external_action_taken"])
            self.assertFalse(report["media_spend_authorised"])
            self.assertFalse(report["creative_diagnostics"][0]["creative_level_performance_available"])

    def test_persisted_report_is_idempotent_and_request_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service_with_history(directory)
            arguments = {
                "cadence": "daily",
                "request_id": "daily-2026-09-29",
                "generated_at": "2026-09-29T08:00:00Z",
            }
            first = service.persist_monitoring_report(**arguments)
            count = len(service.journal.read_all())
            replay = service.persist_monitoring_report(**arguments)
            self.assertEqual(first, replay)
            self.assertEqual(len(service.journal.read_all()), count)
            self.assertEqual(service.monitoring_reports(cadence="daily"), (first,))
            with self.assertRaisesRegex(MediaControlError, "different request"):
                service.persist_monitoring_report(
                    cadence="weekly", request_id="daily-2026-09-29",
                    generated_at="2026-09-29T08:00:00Z",
                )

    def test_tony_daily_monitor_is_read_only_and_actionable(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service_with_history(directory)
            result = TonyMediaCommandService(_Fallback(), service).execute(
                "/media northstar-test-co daily", ()
            )
            self.assertEqual(result.status, "attention_required")
            self.assertIn("Observed facts", result.message)
            self.assertFalse(result.data["external_action_taken"])


if __name__ == "__main__":
    unittest.main()

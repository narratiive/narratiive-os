from __future__ import annotations

import unittest

from runtime.tony_execution_readiness import (
    build_controlled_integration_report,
    build_execution_readiness_report,
    render_execution_readiness,
)


class TonyExecutionReadinessTests(unittest.TestCase):
    def test_report_fails_closed_and_names_exact_missing_surfaces(self):
        report = build_execution_readiness_report({})
        self.assertFalse(report.ready)
        self.assertEqual(
            report.missing_workers,
            ("Claude", "Gmail", "Google Calendar", "Google Drive", "Notion", "Fireflies"),
        )
        rendered = render_execution_readiness(report)
        self.assertIn("TONY_DISPATCH_GMAIL_URL", rendered)
        self.assertIn("TONY_DISPATCH_GOOGLE_CALENDAR_URL", rendered)
        self.assertIn("TONY_DISPATCH_GOOGLE_DRIVE_URL", rendered)
        self.assertIn("TONY_DISPATCH_NOTION_URL", rendered)
        self.assertIn("TONY_DISPATCH_FIREFLIES_URL", rendered)
        self.assertNotIn("secret", rendered.casefold())

    def test_http_dispatchers_are_ready_without_requiring_optional_tokens(self):
        env = {
            "TONY_DISPATCH_CLAUDE_URL": "http://127.0.0.1:9001/claude",
            "TONY_DISPATCH_GMAIL_URL": "http://127.0.0.1:9002/gmail",
            "TONY_DISPATCH_GOOGLE_CALENDAR_URL": "http://127.0.0.1:9003/calendar",
            "TONY_DISPATCH_GOOGLE_DRIVE_URL": "http://127.0.0.1:9004/drive",
            "TONY_DISPATCH_NOTION_URL": "http://127.0.0.1:9005/notion",
            "TONY_DISPATCH_FIREFLIES_URL": "http://127.0.0.1:9006/fireflies",
        }
        report = build_execution_readiness_report(env)
        self.assertTrue(report.ready)
        self.assertEqual(report.missing_workers, ())
        self.assertTrue(all(worker.mode == "http" for worker in report.workers))

    def test_direct_claude_api_requires_explicit_mode_model_and_key(self):
        report = build_execution_readiness_report({"TONY_DISPATCH_CLAUDE_MODE": "anthropic_api"})
        claude = report.workers[0]
        self.assertFalse(claude.configured)
        self.assertEqual(claude.mode, "anthropic_api")
        self.assertIn("TONY_DISPATCH_CLAUDE_MODEL", claude.missing)
        self.assertIn("ANTHROPIC_API_KEY or TONY_DISPATCH_CLAUDE_API_KEY", claude.missing)

        ready = build_execution_readiness_report(
            {
                "TONY_DISPATCH_CLAUDE_MODE": "anthropic_api",
                "TONY_DISPATCH_CLAUDE_MODEL": "claude-model",
                "ANTHROPIC_API_KEY": "not-rendered",
                "TONY_DISPATCH_GMAIL_URL": "http://gmail",
                "TONY_DISPATCH_GOOGLE_CALENDAR_URL": "http://calendar",
                "TONY_DISPATCH_GOOGLE_DRIVE_URL": "http://drive",
                "TONY_DISPATCH_NOTION_URL": "http://notion",
                "TONY_DISPATCH_FIREFLIES_URL": "http://fireflies",
            }
        )
        self.assertTrue(ready.ready)
        rendered = render_execution_readiness(ready)
        self.assertNotIn("not-rendered", rendered)
        self.assertIn("OK — Claude (anthropic_api)", rendered)

    def test_controlled_integration_points_keep_writes_approval_gated(self):
        integrations = {
            item.surface: item
            for item in build_controlled_integration_report(
                {
                    "TONY_DISPATCH_GMAIL_URL": "http://gmail",
                    "TONY_DISPATCH_GOOGLE_CALENDAR_URL": "http://calendar",
                    "TONY_DISPATCH_NOTION_URL": "http://notion",
                }
            )
        }

        self.assertTrue(integrations["Gmail"].configured)
        self.assertIn("send_reviewed_email", integrations["Gmail"].approval_gated_operations)
        self.assertIn("create_recipient_confirmed_meeting", integrations["Google Calendar"].approval_gated_operations)
        self.assertIn("project_workflow_state", integrations["Notion"].approval_gated_operations)
        self.assertNotIn("send_reviewed_email", integrations["Gmail"].autonomous_operations)


if __name__ == "__main__":
    unittest.main()

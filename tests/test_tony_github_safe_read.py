from __future__ import annotations

import unittest

from runtime.github_work import GitHubConfig
from runtime.tony_dispatch_adapters import _GitHubReadDispatcher


class FakeGitHubClient:
    def list_open_pull_requests(self):
        return [{"id": 1, "number": 12, "title": "SAFE pull", "state": "open", "html_url": "https://github.invalid/pull/12"}]

    def list_open_issues(self):
        return [
            {"id": 2, "number": 14, "title": "SAFE issue", "state": "open", "html_url": "https://github.invalid/issues/14"},
            {"id": 3, "number": 12, "title": "pull shadow", "pull_request": {}},
        ]

    def get_pull_request(self, number):
        return {"id": 1, "number": number, "title": "SAFE pull", "head": {"sha": "abc"}}

    def list_check_runs(self, head_sha):
        return [{"id": 4, "name": "tests", "status": "completed", "conclusion": "success"}]


class TonyGitHubSafeReadTests(unittest.TestCase):
    def setUp(self):
        self.dispatcher = _GitHubReadDispatcher(
            GitHubConfig(repository="narratiive/narratiive-os", workspace_id="agency", matt_login="matt"),
            FakeGitHubClient(),
        )

    def test_overview_is_bounded_read_only_evidence(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "inspect",
            "target": {"max_results": 5},
        })
        self.assertTrue(result["verified"])
        self.assertEqual(result["mutation_count"], 0)
        self.assertEqual(result["pull_requests"][0]["number"], 12)
        self.assertEqual(result["issues"][0]["number"], 14)
        self.assertEqual(result["record_ids"], ["12", "14"])

    def test_exact_pull_includes_checks_without_write(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "inspect",
            "target": {"pull_number": 12},
        })
        self.assertEqual(result["source_id"], "github:narratiive/narratiive-os:pull:12")
        self.assertEqual(result["checks"][0]["conclusion"], "success")
        self.assertEqual(result["mutation_count"], 0)


if __name__ == "__main__":
    unittest.main()

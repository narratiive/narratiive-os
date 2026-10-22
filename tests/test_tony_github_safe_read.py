from __future__ import annotations

import unittest

from runtime.github_work import GitHubConfig
from runtime.tony_dispatch_adapters import _GitHubReadDispatcher

KNOWLEDGE_REPOSITORY = "narratiive/" + "narratiive-" + "knowledge"
KNOWLEDGE_NAME = "narratiive-" + "knowledge"


class FakeGitHubClient:
    def list_repositories(self):
        return [
            {"id": 10, "name": "narratiive-os", "full_name": "narratiive/narratiive-os", "private": True},
            {"id": 11, "name": KNOWLEDGE_NAME, "full_name": KNOWLEDGE_REPOSITORY, "private": True},
            {"id": 12, "name": "other", "full_name": "other/other", "private": True},
        ]

    def get_repository_content(self, repository, path=""):
        return {
            "name": path or "README.md",
            "path": path or "README.md",
            "type": "file",
            "size": 4,
            "sha": "abc",
            "encoding": "base64",
            "content": "U0FGRQ==",
        }

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

    def test_lists_only_repositories_for_configured_owner(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "list",
            "target": {"owner": "narratiive"},
        })
        self.assertEqual(
            result["record_ids"],
            ["narratiive/narratiive-os", KNOWLEDGE_REPOSITORY],
        )
        self.assertEqual(result["mutation_count"], 0)

    def test_reads_repository_file_content_without_write(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "get_content",
            "target": {
                "repository": KNOWLEDGE_REPOSITORY,
                "path": "README.md",
            },
        })
        self.assertEqual(result["repository"], KNOWLEDGE_REPOSITORY)
        self.assertEqual(result["content"]["text"], "SAFE")
        self.assertEqual(result["mutation_count"], 0)

    def test_reads_short_repository_name_with_explicit_owner(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "get_content",
            "target": {
                "owner": "narratiive",
                "repo": KNOWLEDGE_NAME,
                "path": "README.md",
            },
        })
        self.assertEqual(result["repository"], KNOWLEDGE_REPOSITORY)
        self.assertEqual(result["content"]["text"], "SAFE")

    def test_fetch_accepts_full_name_for_repository_content(self):
        result = self.dispatcher({
            "execution_mode": "autonomous_read",
            "operation": "fetch",
            "target": {
                "full_name": "narratiive/narratiive-os",
                "path": "README.md",
            },
        })
        self.assertEqual(result["repository"], "narratiive/narratiive-os")
        self.assertEqual(result["content"]["text"], "SAFE")

    def test_rejects_repository_outside_configured_owner(self):
        with self.assertRaisesRegex(Exception, "configured owner"):
            self.dispatcher({
                "execution_mode": "autonomous_read",
                "operation": "get_content",
                "target": {"repository": "other/private", "path": "README.md"},
            })


if __name__ == "__main__":
    unittest.main()

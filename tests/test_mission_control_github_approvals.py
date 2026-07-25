import unittest

from runtime.github_work import GitHubWorkItem, GitHubWorkSnapshot
from runtime.mission_control import MissionControlBuilder
from runtime.progress_engine import ProgressSnapshot
from runtime.repository_validator import ValidationReport


class MissionControlGitHubApprovalsTests(unittest.TestCase):
    @staticmethod
    def progress() -> ProgressSnapshot:
        return ProgressSnapshot(
            status="healthy",
            campaigns=(),
            validation=ValidationReport(
                status="pass",
                objects_validated=0,
                errors=(),
                warnings=(),
            ),
        )

    @staticmethod
    def github_snapshot(*items: GitHubWorkItem) -> GitHubWorkSnapshot:
        return GitHubWorkSnapshot(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            observed_at="2026-07-25T18:00:00Z",
            baseline_status="unavailable",
            baseline_artifact_id="",
            open_pull_requests=items,
            active_issues=(),
            blocked=(),
            matt_approval_required=items,
            changes_since_previous_brief=(),
        )

    def test_github_review_requests_are_visible_as_mission_control_approvals(self) -> None:
        pull_request = GitHubWorkItem(
            kind="pull_request",
            number=81,
            title="Review Tony reliability change",
            url="https://github.com/narratiive/narratiive-os/pull/81",
            state="open",
            author="tony",
            created_at="2026-07-25T17:00:00Z",
            updated_at="2026-07-25T18:00:00Z",
            requested_reviewers=("narratiive",),
        )

        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-25T18:00:00Z",
            progress=self.progress(),
            approvals_required=("client:alpha:approve",),
            github_work=self.github_snapshot(pull_request),
        )

        self.assertEqual(
            snapshot.approvals_required,
            (
                "client:alpha:approve",
                "github:pull_request:81:https://github.com/narratiive/narratiive-os/pull/81",
            ),
        )

    def test_duplicate_explicit_and_github_approvals_are_deterministic(self) -> None:
        pull_request = GitHubWorkItem(
            kind="pull_request",
            number=82,
            title="Review Mission Control change",
            url="https://github.com/narratiive/narratiive-os/pull/82",
            state="open",
            author="tony",
            created_at="2026-07-25T17:00:00Z",
            updated_at="2026-07-25T18:00:00Z",
            requested_reviewers=("narratiive",),
        )
        approval = (
            "github:pull_request:82:"
            "https://github.com/narratiive/narratiive-os/pull/82"
        )

        snapshot = MissionControlBuilder().build(
            generated_at="2026-07-25T18:00:00Z",
            progress=self.progress(),
            approvals_required=(approval, approval, ""),
            github_work=self.github_snapshot(pull_request),
        )

        self.assertEqual(snapshot.approvals_required, (approval,))


if __name__ == "__main__":
    unittest.main()

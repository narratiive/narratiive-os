import unittest

from runtime.github_mission_control_projection import project_github_workstreams
from runtime.github_work import GitHubWorkItem, GitHubWorkSnapshot


class GitHubMissionControlProjectionTests(unittest.TestCase):
    @staticmethod
    def item(
        *,
        kind: str,
        number: int,
        title: str,
        blocker_reasons: tuple[str, ...] = (),
    ) -> GitHubWorkItem:
        return GitHubWorkItem(
            kind=kind,
            number=number,
            title=title,
            url=f"https://github.test/{kind}/{number}",
            state="open",
            author="narratiive",
            created_at="2026-07-29T17:00:00Z",
            updated_at="2026-07-29T18:00:00Z",
            blocker_reasons=blocker_reasons,
        )

    @staticmethod
    def snapshot(
        *,
        pull_requests: tuple[GitHubWorkItem, ...] = (),
        issues: tuple[GitHubWorkItem, ...] = (),
        blocked: tuple[GitHubWorkItem, ...] = (),
        approvals: tuple[GitHubWorkItem, ...] = (),
    ) -> GitHubWorkSnapshot:
        return GitHubWorkSnapshot(
            repository="narratiive/narratiive-os",
            workspace_id="agency",
            observed_at="2026-07-29T18:00:00Z",
            baseline_status="unavailable",
            baseline_artifact_id="",
            open_pull_requests=pull_requests,
            active_issues=issues,
            blocked=blocked,
            matt_approval_required=approvals,
            changes_since_previous_brief=(),
        )

    def test_projects_open_repository_work_deterministically(self) -> None:
        issue = self.item(kind="issue", number=54, title="Mission Control snapshot")
        pull_request = self.item(
            kind="pull_request",
            number=67,
            title="GitHub work awareness",
        )

        workstreams = project_github_workstreams(
            self.snapshot(pull_requests=(pull_request,), issues=(issue,))
        )

        self.assertEqual(
            [item.workstream_id for item in workstreams],
            ["github:issue:54", "github:pull_request:67"],
        )
        self.assertEqual(workstreams[0].title, "Issue #54: Mission Control snapshot")
        self.assertEqual(workstreams[1].title, "PR #67: GitHub work awareness")
        self.assertTrue(all(item.owner == "repository" for item in workstreams))
        self.assertTrue(all(item.evidence for item in workstreams))

    def test_preserves_blockers_and_review_decisions_without_inference(self) -> None:
        blocked = self.item(
            kind="issue",
            number=94,
            title="Interruption policy extraction",
            blocker_reasons=("label:blocked", "external dependency"),
        )
        review = self.item(
            kind="pull_request",
            number=105,
            title="Agency-first executive brief",
        )

        workstreams = project_github_workstreams(
            self.snapshot(
                pull_requests=(review,),
                issues=(blocked,),
                blocked=(blocked,),
                approvals=(review,),
            )
        )

        self.assertEqual(workstreams[0].state, "blocked")
        self.assertEqual(
            workstreams[0].blocker,
            "label:blocked; external dependency",
        )
        self.assertEqual(workstreams[1].state, "tested")
        self.assertEqual(
            workstreams[1].next_action,
            "Record Matt's review decision.",
        )

    def test_missing_snapshot_fails_closed(self) -> None:
        self.assertEqual(project_github_workstreams(None), ())


if __name__ == "__main__":
    unittest.main()

from runtime.github_work import GitHubWorkAdapter


def test_reports_open_pull_requests_and_issues_without_duplication() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        pull_requests=(
            {"number": 64, "title": "Canonical terminology", "url": "https://github.test/pull/64"},
        ),
        issues=(
            {"number": 64, "title": "PR mirror", "url": "https://github.test/issues/64"},
            {"number": 66, "title": "GitHub awareness", "url": "https://github.test/issues/66"},
        ),
    )

    assert [item.number for item in snapshot.pull_requests] == [64]
    assert [item.number for item in snapshot.issues] == [66]
    assert snapshot.evidence == (
        "https://github.test/pull/64",
        "https://github.test/issues/66",
    )


def test_identifies_explicit_review_requests() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        pull_requests=(
            {
                "number": 64,
                "title": "Canonical terminology",
                "url": "https://github.test/pull/64",
                "review_requested": True,
            },
        ),
    )

    assert snapshot.approvals_required == (
        "Review pr #64: Canonical terminology — https://github.test/pull/64",
    )
    assert snapshot.workstreams()[0].state == "tested"


def test_failed_ci_is_a_deterministic_blocker() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        pull_requests=(
            {
                "number": 70,
                "title": "Broken change",
                "url": "https://github.test/pull/70",
                "ci_status": "failure",
            },
        ),
    )

    assert snapshot.blockers == ("github:pr:70:CI failure",)
    workstream = snapshot.workstreams()[0]
    assert workstream.state == "blocked"
    assert workstream.blocker == "CI failure"


def test_merge_conflict_is_reported_when_ci_is_not_failed() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        pull_requests=(
            {
                "number": 71,
                "title": "Conflicted change",
                "url": "https://github.test/pull/71",
                "ci_status": "success",
                "mergeable": False,
            },
        ),
    )

    assert snapshot.blockers == ("github:pr:71:merge conflict",)


def test_blocked_issue_label_is_reported() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        issues=(
            {
                "number": 72,
                "title": "External dependency",
                "url": "https://github.test/issues/72",
                "labels": ("blocked",),
            },
        ),
    )

    assert snapshot.blockers == ("github:issue:72:blocked label",)


def test_unavailable_source_fails_closed() -> None:
    snapshot = GitHubWorkAdapter().build(
        repository="narratiive/narratiive-os",
        pull_requests=(
            {"number": 64, "title": "Hidden", "url": "https://github.test/pull/64"},
        ),
        available=False,
        error="connector unavailable",
    )

    assert snapshot.state == "not_connected"
    assert snapshot.pull_requests == ()
    assert snapshot.issues == ()
    assert snapshot.workstreams() == ()
    assert snapshot.connection() == {"state": "not_connected"}
    assert snapshot.error == "connector unavailable"

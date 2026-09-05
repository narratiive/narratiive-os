from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from runtime.research_engine import (
    EvidenceSource,
    EvidenceSourcePolicy,
    ResearchEngine,
    ResearchJob,
)


class ResearchWorkflowAdapter:
    """Execute approved, workspace-scoped sources through the existing Research Engine."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.engine = ResearchEngine(self.root)

    def __call__(self, contract: dict[str, Any]) -> dict[str, Any]:
        context = contract.get("workflow_context")
        if not isinstance(context, Mapping) or context.get("workflow_id") != "growth_sprint_to_research_engine":
            raise ValueError("research adapter received an invalid workflow contract")
        tasks = self._tasks(contract.get("research_requirements"))
        workspace_id = str(context.get("workspace_id") or "").strip()
        if not workspace_id:
            raise ValueError("research adapter requires an explicit workspace identity")
        sources = self._sources(contract.get("research_sources"), workspace_id)
        query = " | ".join(task["question"] for task in tasks)
        run = self.engine.run(
            ResearchJob(
                job_id=str(context.get("run_id") or "research-run"),
                workspace_id=workspace_id,
                query=query,
                sources=sources,
                missing_inputs=tuple(
                    str(item) for item in _as_list(contract.get("research_requirements", {}).get("known_gaps"))
                ) if isinstance(contract.get("research_requirements"), Mapping) else (),
                lineage=(str(context.get("correlation_id") or ""),),
            )
        )
        pack = run.evidence_pack.as_dict()
        findings = [
            {
                "statement": (
                    f"Approved source {record.get('source_id')} records: "
                    f"{record.get('excerpt') or record.get('content')}"
                ),
                "classification": "fact",
                "evidence_refs": [record.get("evidence_id")],
                "source_refs": list(record.get("source_ids") or [record.get("source_id")]),
            }
            for record in pack.get("records", [])
            if isinstance(record, Mapping) and (record.get("excerpt") or record.get("content"))
        ]
        provenance = [
            item
            for record in pack.get("records", [])
            if isinstance(record, Mapping)
            for item in record.get("provenance", [])
            if isinstance(item, Mapping)
        ]
        gaps = list(dict.fromkeys([*run.blockers, *pack.get("missing_inputs", [])]))
        contradictions = self._contradictions(sources)
        return {
            "research_tasks": tasks,
            "evidence_pack": pack,
            "source_provenance": provenance,
            "consolidated_findings": findings,
            "contradictions": contradictions,
            "research_gaps": gaps,
            "further_research_requests": [
                {"gap": gap, "status": "requires_additional_approved_source"} for gap in gaps
            ],
            "fact_interpretation_hypothesis_lineage": {
                "facts": findings,
                "interpretations": [],
                "hypotheses": [],
            },
            "external_action_taken": False,
        }

    @staticmethod
    def _tasks(value: Any) -> list[dict[str, Any]]:
        candidates = value.get("workstreams_and_questions") if isinstance(value, Mapping) else value
        tasks: list[dict[str, Any]] = []
        for index, item in enumerate(_as_list(candidates), start=1):
            if isinstance(item, Mapping):
                workstream = str(item.get("workstream") or f"research-{index}").strip()
                questions = _as_list(item.get("questions") or item.get("question"))
            else:
                workstream = f"research-{index}"
                questions = [item]
            for question_index, question in enumerate(questions, start=1):
                text = str(question or "").strip()
                if text:
                    tasks.append({
                        "task_id": f"task-{index}-{question_index}",
                        "workstream": workstream,
                        "question": text,
                        "required_capability": "market_research",
                        "assigned_worker": "narratiive-research-engine",
                    })
        if not tasks:
            raise ValueError("research requirements contain no actionable questions")
        return tasks

    @staticmethod
    def _sources(value: Any, workspace_id: str) -> tuple[EvidenceSource, ...]:
        sources: list[EvidenceSource] = []
        for item in _as_list(value):
            if not isinstance(item, Mapping):
                raise ValueError("research source must be a structured object")
            policy = item.get("policy") if isinstance(item.get("policy"), Mapping) else {}
            if policy.get("approved") is not True:
                raise ValueError("research source is not approved")
            sources.append(
                EvidenceSource(
                    source_id=str(item.get("source_id") or "").strip(),
                    workspace_id=workspace_id,
                    source_type=str(item.get("source_type") or "").strip(),
                    uri=str(item.get("uri") or item.get("location") or "").strip(),
                    title=str(item.get("title") or "").strip(),
                    policy=EvidenceSourcePolicy(
                        approved=True,
                        allowed_domains=tuple(str(domain) for domain in _as_list(policy.get("allowed_domains"))),
                        allowed_schemes=tuple(str(scheme) for scheme in _as_list(policy.get("allowed_schemes"))) or ("https",),
                        max_bytes=int(policy.get("max_bytes") or 250_000),
                        timeout_seconds=int(policy.get("timeout_seconds") or 10),
                        allow_local_files=policy.get("allow_local_files") is True,
                    ),
                    metadata=dict(item.get("metadata") or {}),
                )
            )
        if not sources or any(not source.source_id or not source.source_type or not source.uri for source in sources):
            raise ValueError("research requires complete approved sources")
        return tuple(sources)

    @staticmethod
    def _contradictions(sources: tuple[EvidenceSource, ...]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, list[str]]] = {}
        for source in sources:
            claim_key = str(source.metadata.get("claim_key") or "").strip()
            stance = str(source.metadata.get("stance") or "").strip()
            if claim_key and stance:
                grouped.setdefault(claim_key, {}).setdefault(stance, []).append(source.source_id)
        return [
            {"claim_key": claim_key, "stances": stances, "status": "unresolved"}
            for claim_key, stances in grouped.items()
            if len(stances) > 1
        ]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]

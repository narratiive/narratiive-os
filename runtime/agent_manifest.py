from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_METADATA_PATTERN = re.compile(r"<!--\s*([A-Z0-9_]+)\s*:\s*(.*?)\s*-->")
_HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class AgentManifest:
    agent_id: str
    version: str
    source_path: str
    instructions: str
    metadata: Mapping[str, str]
    sections: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if not self.instructions.strip():
            raise ValueError("agent instructions must not be empty")

    def section(self, name: str) -> str:
        try:
            return self.sections[name]
        except KeyError as exc:
            raise KeyError(f"agent section not found: {name}") from exc


def load_agent_manifest(path: str | Path) -> AgentManifest:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    return parse_agent_manifest(text, source_path=str(source))


def parse_agent_manifest(text: str, *, source_path: str = "<memory>") -> AgentManifest:
    metadata = {key: value.strip() for key, value in _METADATA_PATTERN.findall(text)}
    agent_id = metadata.get("AI_AGENT_ID", "").strip()
    version = metadata.get("AI_AGENT_VERSION", "1.0").strip()
    if not agent_id:
        raise ValueError("agent manifest is missing AI_AGENT_ID metadata")

    sections = _extract_sections(text)
    required = {"Purpose", "Inputs", "Outputs", "Rules", "Workflow"}
    missing = sorted(required - sections.keys())
    if missing:
        raise ValueError(f"agent manifest missing required sections: {', '.join(missing)}")

    return AgentManifest(
        agent_id=agent_id,
        version=version,
        source_path=source_path,
        instructions=text.strip(),
        metadata=metadata,
        sections=sections,
    )


def _extract_sections(text: str) -> dict[str, str]:
    matches = list(_HEADING_PATTERN.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if name in sections:
            raise ValueError(f"duplicate agent section: {name}")
        sections[name] = body
    return sections

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from runtime.inbound_leads import (
    CANONICAL_NOTION_LEADS_DATA_SOURCE_ID,
    FileInboundLeadStore,
    InboundLead,
)


class NotionLeadSourceError(RuntimeError):
    """Raised when the canonical Notion Leads source cannot be trusted."""


OpenUrl = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class NotionLeadConfig:
    token: str
    data_source_id: str = CANONICAL_NOTION_LEADS_DATA_SOURCE_ID
    api_base: str = "https://api.notion.com"
    notion_version: str = "2026-03-11"
    page_size: int = 100
    max_pages: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "NotionLeadConfig":
        token = ""
        for name in (
            "NARRATIIVE_NOTION_TOKEN",
            "NOTION_API_TOKEN",
            "NOTION_API_KEY",
            "NOTION_TOKEN",
        ):
            token = str(env.get(name, "")).strip()
            if token:
                break
        if not token:
            raise NotionLeadSourceError(
                "Canonical Notion lead access is not configured. Set NARRATIIVE_NOTION_TOKEN in runtime.env."
            )
        data_source_id = (
            str(env.get("NARRATIIVE_NOTION_LEADS_DATA_SOURCE_ID", "")).strip()
            or CANONICAL_NOTION_LEADS_DATA_SOURCE_ID
        )
        api_base = str(env.get("NARRATIIVE_NOTION_API_BASE", "")).strip() or "https://api.notion.com"
        return cls(token=token, data_source_id=data_source_id, api_base=api_base.rstrip("/"))


class NotionLeadSource:
    """Authoritative read adapter for Leads — CANONICAL.

    Notion is the commercial source of truth. The local FileInboundLeadStore is
    only a synchronized cache used for resilience and must never override a
    successful Notion read.
    """

    def __init__(
        self,
        config: NotionLeadConfig,
        *,
        cache: FileInboundLeadStore | None = None,
        opener: OpenUrl = urlopen,
    ) -> None:
        self.config = config
        self.cache = cache
        self.opener = opener

    def read(self) -> tuple[InboundLead, ...]:
        results: list[InboundLead] = []
        cursor: str | None = None
        for _ in range(self.config.max_pages):
            payload = self._query_page(cursor)
            raw_results = payload.get("results", [])
            if not isinstance(raw_results, list):
                raise NotionLeadSourceError("Notion returned an invalid leads result set")
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                try:
                    lead = InboundLead.from_mapping(item)
                except ValueError:
                    continue
                results.append(lead)
                if self.cache is not None:
                    self.cache.upsert(lead)
            if payload.get("has_more") is not True:
                break
            next_cursor = payload.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor.strip():
                raise NotionLeadSourceError("Notion pagination was incomplete")
            cursor = next_cursor

        deduped = {lead.lead_id: lead for lead in results}
        return tuple(
            sorted(
                deduped.values(),
                key=lambda item: (item.created_at, item.lead_id),
                reverse=True,
            )
        )

    def _query_page(self, cursor: str | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "page_size": self.config.page_size,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        }
        if cursor:
            body["start_cursor"] = cursor
        raw_body = json.dumps(body).encode("utf-8")
        request = Request(
            f"{self.config.api_base}/v1/data_sources/{self.config.data_source_id}/query",
            data=raw_body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.config.token}",
                "Notion-Version": self.config.notion_version,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self.opener(request, timeout=12.0) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise NotionLeadSourceError(
                f"Notion leads query returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise NotionLeadSourceError(f"Notion leads query failed: {exc}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise NotionLeadSourceError("Notion leads query returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise NotionLeadSourceError("Notion leads query returned an invalid response")
        return payload


def build_authoritative_lead_loader(
    cache: FileInboundLeadStore,
    *,
    env: Mapping[str, str] | None = None,
) -> Callable[[], tuple[InboundLead, ...]]:
    """Build the authoritative lead loader used by Tony.

    A configured Notion connection is required. We deliberately fail closed when
    Notion cannot be read instead of falling back to an empty local cache and
    making a false claim that there are no leads.
    """
    config = NotionLeadConfig.from_env(os.environ if env is None else env)
    return NotionLeadSource(config, cache=cache).read

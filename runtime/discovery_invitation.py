from __future__ import annotations

import html
import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


TEMPLATE_VERSION = "narratiive-discovery-invitation-v1"
TEMPLATE_PATH = Path(__file__).with_name("email_templates") / f"{TEMPLATE_VERSION}.html"
_BOOKING_HOSTS = {"calendar.app.google", "calendar.google.com"}


class DiscoveryInvitationError(ValueError):
    """The invitation cannot be rendered safely from the supplied evidence."""


@dataclass(frozen=True, slots=True)
class RenderedDiscoveryInvitation:
    subject: str
    body: str
    email_html: str
    template_version: str = TEMPLATE_VERSION


def render_discovery_invitation(
    invitation: Mapping[str, Any],
    *,
    booking_url: str,
) -> RenderedDiscoveryInvitation:
    """Render one evidence-bound plain-text/HTML invitation from Groundwork data."""
    if not isinstance(invitation, Mapping):
        raise DiscoveryInvitationError("discovery invitation fields are missing")

    company = _required_text(invitation, "company_name")
    first_name = _required_text(invitation, "first_name")
    subject = _required_text(invitation, "email_subject")
    headline_lines = _required_text_list(invitation, "headline_lines", minimum=2, maximum=3)
    intro_paragraphs = _required_text_list(invitation, "intro_paragraphs", minimum=2, maximum=3)
    source_urls = _source_urls(invitation.get("groundwork_sources"))
    starters = _conversation_starters(invitation.get("conversation_starters"), source_urls)
    visual_url = _public_https_url(_required_text(invitation, "brand_visual_url"), "brand visual")
    visual_alt = _required_text(invitation, "brand_visual_alt")
    booking = _booking_url(booking_url)

    starter_rows = "".join(
        _render_starter(index, starter["heading"], starter["body"], index < 3)
        for index, starter in enumerate(starters, start=1)
    )
    replacements = {
        "{{COMPANY_NAME}}": html.escape(company),
        "{{FIRST_NAME}}": html.escape(first_name),
        "{{EMAIL_SUBJECT}}": html.escape(subject),
        "{{HEADLINE}}": "<br>".join(html.escape(line) for line in headline_lines),
        "{{INTRO_PARAGRAPHS}}": "".join(
            f'<p style="font-size:16px;line-height:1.52;margin:0 0 14px">{html.escape(paragraph)}</p>'
            for paragraph in intro_paragraphs
        ),
        "{{BRAND_VISUAL_URL}}": html.escape(visual_url, quote=True),
        "{{BRAND_VISUAL_ALT}}": html.escape(visual_alt, quote=True),
        "{{CONVERSATION_STARTERS}}": starter_rows,
        "{{BOOKING_URL}}": html.escape(booking, quote=True),
    }
    rendered_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker, value in replacements.items():
        rendered_html = rendered_html.replace(marker, value)
    if re.search(r"\{\{[A-Z_]+\}\}", rendered_html):
        raise DiscoveryInvitationError("discovery invitation template is incomplete")

    body = _render_plain_text(
        first_name=first_name,
        intro_paragraphs=intro_paragraphs,
        starters=starters,
        booking_url=booking,
    )
    return RenderedDiscoveryInvitation(subject=subject, body=body, email_html=rendered_html)


def _required_text(value: Mapping[str, Any], key: str) -> str:
    rendered = str(value.get(key) or "").strip()
    if not rendered or any(ord(character) < 32 for character in rendered):
        raise DiscoveryInvitationError(f"{key.replace('_', ' ')} is missing or unsafe")
    return rendered


def _required_text_list(
    value: Mapping[str, Any], key: str, *, minimum: int, maximum: int
) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list) or not minimum <= len(items) <= maximum:
        raise DiscoveryInvitationError(f"{key.replace('_', ' ')} must contain {minimum}-{maximum} items")
    rendered = [str(item or "").strip() for item in items]
    if any(not item or any(ord(character) < 32 for character in item) for item in rendered):
        raise DiscoveryInvitationError(f"{key.replace('_', ' ')} contains missing or unsafe text")
    return rendered


def _source_urls(value: Any) -> set[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise DiscoveryInvitationError("one to eight Groundwork sources are required")
    urls: set[str] = set()
    for source in value:
        if not isinstance(source, Mapping):
            raise DiscoveryInvitationError("Groundwork source metadata is invalid")
        url = _public_http_url(str(source.get("url") or "").strip(), "Groundwork source")
        urls.add(url.rstrip("/"))
    if len(urls) != len(value):
        raise DiscoveryInvitationError("Groundwork sources must be distinct")
    return urls


def _conversation_starters(value: Any, source_urls: set[str]) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != 3:
        raise DiscoveryInvitationError("exactly three evidence-bound conversation starters are required")
    rendered = []
    for item in value:
        if not isinstance(item, Mapping):
            raise DiscoveryInvitationError("conversation starter metadata is invalid")
        heading = _required_text(item, "heading")
        body = _required_text(item, "body")
        references = item.get("source_urls")
        if not isinstance(references, list) or not references:
            raise DiscoveryInvitationError("each conversation starter requires Groundwork source URLs")
        normalised = {str(reference or "").strip().rstrip("/") for reference in references}
        if not normalised or not normalised.issubset(source_urls):
            raise DiscoveryInvitationError("conversation starter evidence is not present in Groundwork")
        rendered.append({"heading": heading, "body": body})
    return rendered


def _booking_url(value: str) -> str:
    rendered = _public_https_url(str(value or "").strip(), "booking URL")
    if (urlsplit(rendered).hostname or "").casefold() not in _BOOKING_HOSTS:
        raise DiscoveryInvitationError("booking URL must use the configured Google Calendar destination")
    return rendered


def _public_https_url(value: str, label: str) -> str:
    rendered = _public_http_url(value, label)
    if urlsplit(rendered).scheme.casefold() != "https":
        raise DiscoveryInvitationError(f"{label} must use HTTPS")
    return rendered


def _public_http_url(value: str, label: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise DiscoveryInvitationError(f"{label} is invalid") from exc
    host = parsed.hostname or ""
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
        or any(character.isspace() for character in value)
    ):
        raise DiscoveryInvitationError(f"{label} is invalid")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or host.casefold() == "localhost":
            raise DiscoveryInvitationError(f"{label} must use a public host")
    else:
        if not address.is_global:
            raise DiscoveryInvitationError(f"{label} must use a public host")
    return value


def _render_starter(number: int, heading: str, body: str, divider: bool) -> str:
    border = "border-bottom:1px solid #c8c2bc;" if divider else ""
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="{border}"><tr>'
        f'<td valign="top" style="padding:20px 14px 20px 0;width:60px"><div class="circle" style="background:#e4602e;border-radius:50%;color:#fffdf9;font-size:17px;font-weight:bold;height:50px;line-height:50px;text-align:center;width:50px">{number:02d}</div></td>'
        f'<td class="question-copy" style="padding:20px 0"><strong style="font-size:16px;letter-spacing:.3px">{html.escape(heading)}</strong><p style="font-size:16px;line-height:1.45;margin:5px 0 0">{html.escape(body)}</p></td>'
        "</tr></table>"
    )


def _render_plain_text(
    *,
    first_name: str,
    intro_paragraphs: Sequence[str],
    starters: Sequence[Mapping[str, str]],
    booking_url: str,
) -> str:
    questions = "\n\n".join(
        f"{index:02d} / {item['heading']}\n{item['body']}"
        for index, item in enumerate(starters, start=1)
    )
    return (
        f"Hi {first_name},\n\n"
        + "\n\n".join(intro_paragraphs)
        + "\n\nTHREE THINGS WE'D LOVE TO EXPLORE\n\n"
        + questions
        + "\n\nLET'S FIND OUT TOGETHER.\n\n"
        "I'd love to spend 30 minutes exploring what's possible. We'll bring an outside perspective, "
        "you bring the inside story, and we'll see where the most valuable opportunity emerges.\n\n"
        "No pitch deck. No obligation. Just a good conversation.\n\n"
        f"Book a 30-minute conversation: {booking_url}\n\n"
        "Looking forward to meeting you.\n\nMatt Franks\nFounder, Narratiive"
    )

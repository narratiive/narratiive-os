"""Standalone approved-v4 proposal authoring. Does not approve, store or send.

Pass 1 deliberately has no dependency on Tony or workflow persistence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
from typing import Any, Mapping

from PIL import Image
from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

TEMPLATE_VERSION = "fieldwork-v4.1"
TEMPLATE = Path(__file__).resolve().parents[1] / "templates/fieldwork/v4"
REFERENCE_SHA256 = "3dc801365e80af0261d93b26721dfbc3deaa634a3676d5a219ab66c8b8a0d504"
FONT_FILES = {"Serif": "Baskerville.ttc", "Sans": "Arial.ttf", "Bold": "Arial Bold.ttf"}


class FieldworkProposalError(ValueError):
    """An input or layout cannot safely use the approved template."""


@dataclass(frozen=True)
class RenderedFieldworkProposal:
    pdf: bytes
    checksum: str
    template_version: str
    manifest: Mapping[str, Any]


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def validate_inputs(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete, explicit input; never fill copy from Origin defaults.

    Pass 1 authors internal candidates only. It cannot assert commercial approval.
    """
    if not isinstance(data, Mapping):
        raise FieldworkProposalError("Input must be an object")
    data = deepcopy(dict(data))
    contract = json.loads((TEMPLATE / "origin-fictional.json").read_text())
    if set(data) != set(contract) or data.get("template_version") != TEMPLATE_VERSION:
        raise FieldworkProposalError("Complete fieldwork-v4.1 input required")
    for name in ("workspace_id", "client_id"):
        if not isinstance(data[name], str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", data[name]):
            raise FieldworkProposalError(f"Invalid {name}")
    for name in ("client_name", "client_short"):
        if not isinstance(data[name], str) or not data[name].strip() or re.search(r"[<>{}\n\r]", data[name]):
            raise FieldworkProposalError(f"Invalid {name}")
    if not isinstance(data['fictional'], bool):
        raise FieldworkProposalError("fictional must be boolean")
    for name in ("copy", "palette", "images"):
        if not isinstance(data[name], dict) or set(data[name]) != set(contract[name]):
            raise FieldworkProposalError(f"Complete {name} fields required")
    for value in data['copy'].values():
        if not isinstance(value, str) or not value.strip() or len(value) > 2500:
            raise FieldworkProposalError("Copy must contain bounded non-empty text")
        if re.search(r"growth sprint|blueprint lite", value, re.I):
            raise FieldworkProposalError("Legacy product terminology is prohibited")
        # Only the reference line-break markup is supported. Reject inline styling,
        # links, images and placeholders that could bypass the fixed layout.
        plain = value.replace('<br/>', '')
        if '<' in plain or '>' in plain or re.search(r'&(?!amp;|lt;|gt;|quot;|apos;)', plain):
            raise FieldworkProposalError("Only <br/> markup and escaped entities are supported")
        for token in re.findall(r"\{[^}]*\}", value):
            if token not in ('{client_name}', '{client_short}', '{client_upper}'):
                raise FieldworkProposalError("Unknown copy placeholder")
    for colour in data['palette'].values():
        if not isinstance(colour, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", colour):
            raise FieldworkProposalError("Palette values must be hex colours")
    fee = data['proposed_fee']
    if not isinstance(fee, dict) or set(fee) != set(contract['proposed_fee']):
        raise FieldworkProposalError("Exact proposed fee fields required")
    try:
        amount = Decimal(str(fee['amount']))
    except (InvalidOperation, ValueError):
        raise FieldworkProposalError("Invalid fee") from None
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('.01')):
        raise FieldworkProposalError("Fee must be a positive amount with at most two decimals")
    if fee['currency'] != 'GBP' or fee['vat_basis'] != 'excluding VAT' or fee['approved'] is not False:
        raise FieldworkProposalError("Pass 1 supports unapproved GBP fees excluding VAT only")
    if data['copy']['delivery_duration'] != '7 working days':
        raise FieldworkProposalError("Seven-working-day delivery required")
    if data['copy']['fee_status'] != contract['copy']['fee_status']:
        raise FieldworkProposalError("Internal proposed-fee notice must remain visible")
    if data['copy']['review_status'] != ('FICTIONAL / INTERNAL REVIEW' if data['fictional'] else 'DRAFT / INTERNAL REVIEW'):
        raise FieldworkProposalError("Visible internal review status required")
    if data['fictional'] and data['copy']['fictional_notice'] != contract['copy']['fictional_notice']:
        raise FieldworkProposalError("Fictional engagement notice required")
    model = data['commercial_model']
    if not isinstance(model, dict) or set(model) != set(contract['commercial_model']) or model['status'] != 'illustrative_assumptions':
        raise FieldworkProposalError("Explicit illustrative model required in Pass 1")
    for field, maximum in (('accounts', 1000000), ('ramp', 1)):
        values = model[field]
        if not isinstance(values, list) or len(values) != 3 or any(type(v) not in (int, float) or not 0 < v <= maximum for v in values) or values != sorted(values):
            raise FieldworkProposalError(f"Invalid conservative/central/upside {field}")
    if any(type(v) is not int for v in model['accounts']):
        raise FieldworkProposalError("Accounts must be whole numbers")
    revenue = model['annual_account_revenue']
    if type(revenue) is not int or not 0 < revenue < 1e12:
        raise FieldworkProposalError("Positive whole-pound annual account revenue required")
    if any(abs(v * 100 - round(v * 100)) > 1e-8 for v in model['ramp']):
        raise FieldworkProposalError("Ramp percentages must be whole percentages")
    for slot, image in data['images'].items():
        if not isinstance(image, dict) or set(image) != {'path', 'anchor', 'provenance', 'status'}:
            raise FieldworkProposalError(f"Complete image record required: {slot}")
        if any(not isinstance(image[k], str) or not image[k].strip() for k in ('path', 'provenance', 'status')):
            raise FieldworkProposalError("Image path, provenance and status required")
        if not isinstance(image['anchor'], list) or len(image['anchor']) != 2 or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in image['anchor']):
            raise FieldworkProposalError("Image crop anchors must be in [0, 1]")
    return data


def _bound_copy(data: dict[str, Any]) -> dict[str, str]:
    substitutions = dict(client_name=data['client_name'], client_short=data['client_short'], client_upper=data['client_name'].upper())
    try:
        copy = {key: value.format(**substitutions) for key, value in data['copy'].items()}
    except (KeyError, ValueError) as exc:
        raise FieldworkProposalError("Invalid copy placeholder") from exc
    model = data['commercial_model']
    accounts, ramp, revenue = model['accounts'], model['ramp'], model['annual_account_revenue']
    results = [a * revenue * r for a, r in zip(accounts, ramp)]
    money = lambda n: f"£{n / 1000:.0f}k"
    copy['model_central'] = '+' + money(results[1])
    copy['model_sensitivity'] = f"Sensitivity: ~{money(results[0])} to ~{money(results[2])}"
    copy['model_formula'] = f"{accounts[1]} additional accounts × £{revenue:,.0f} net annual account revenue × {ramp[1]:.0%} year-one ramp."
    copy['model_limitations'] = f"{accounts[0]}–{accounts[2]} accounts; {ramp[0]*100:.0f}–{ramp[2]:.0%} ramp. All assumed, not {data['client_short']} results or a forecast. Revenue, not profit; implementation costs separate. No guaranteed return."
    amount = Decimal(str(data['proposed_fee']['amount']))
    formatted = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    copy['fee_display'] = f"£{formatted} ex VAT"
    return copy


def render_fieldwork_proposal(data: Mapping[str, Any], *, asset_root: Path,
                              font_dir: Path = Path('/System/Library/Fonts/Supplemental')) -> RenderedFieldworkProposal:
    """Return deterministic PDF bytes, checksum, template version and manifest.

    asset_root bounds every supplied image path. Exact Baskerville/Arial fonts
    must be provided on non-Mac hosts; there is no substitute-font fallback.
    """
    data = validate_inputs(data)
    asset_root = Path(asset_root).resolve()
    images, image_evidence, identities = {}, {}, set()
    for slot, record in data['images'].items():
        relative = Path(record['path'])
        path = (asset_root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(asset_root) or not path.is_file():
            raise FieldworkProposalError(f"Image outside asset root or missing: {slot}")
        raw = path.read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            identity = _hash(str(image.size).encode() + image.convert('RGB').tobytes())
        if identity in identities:
            raise FieldworkProposalError("Each placement requires a distinct image")
        identities.add(identity)
        images[slot] = dict(record, path=path)
        image_evidence[slot] = dict(record, sha256=_hash(raw))
    fonts = {}
    approved_fonts = json.loads((TEMPLATE / 'font-checksums.json').read_text())
    for name, filename in FONT_FILES.items():
        path = Path(font_dir) / filename
        if not path.is_file():
            raise FieldworkProposalError(f"Approved font unavailable: {filename}")
        fonts[name] = _hash(path.read_bytes())
        if fonts[name] != approved_fonts[filename]:
            raise FieldworkProposalError(f"Approved font checksum mismatch: {filename}")
        pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
    spec = importlib.util.spec_from_file_location('fieldwork_v4_layout', TEMPLATE / 'layout.py')
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)
    limits = json.loads((TEMPLATE / 'layout-limits.json').read_text())
    measured = []
    def check_paragraph(text, x, y, width, height):
        key = f'{x}:{y}:{width}'
        if key not in limits or height > limits[key] + .01:
            raise FieldworkProposalError(f"Text exceeds approved box at {key}; edit copy")
        measured.append(dict(box=key, height=height, maximum=limits[key]))
    def check_line(text, x, y, size, font, tracking=0):
        # The investment heads have 164pt columns; header and footer retain margins.
        width = 164 if y == 713 else 563 - x
        if pdfmetrics.stringWidth(text, font, size) + max(0, len(text)-1)*tracking > width:
            raise FieldworkProposalError(f"Single line exceeds approved box at {x}:{y}")
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(595.28, 841.89), invariant=1)
    canvas.setTitle(f"{data['client_name']} | Fieldwork | Internal review v4")
    canvas.setAuthor('Narratiive - internal review candidate')
    layout.draw(canvas, _bound_copy(data), images, data['palette'], check_paragraph, check_line)
    pdf = buffer.getvalue()
    reader = PdfReader(io.BytesIO(pdf))
    if len(reader.pages) != 2:
        raise FieldworkProposalError("Exactly two pages required")
    text = '\n'.join(page.extract_text() for page in reader.pages)
    if '7 working days' not in text or re.search(r'growth sprint|blueprint lite', text, re.I):
        raise FieldworkProposalError("Rendered content failed product validation")
    if any(data['copy']['review_status'] not in page.extract_text() for page in reader.pages):
        raise FieldworkProposalError("Review notice missing from a page")
    reference = (TEMPLATE / 'reference.pdf').read_bytes()
    if _hash(reference) != REFERENCE_SHA256:
        raise FieldworkProposalError("Approved reference checksum mismatch")
    template_files = {str(p.relative_to(TEMPLATE)): _hash(p.read_bytes()) for p in sorted(TEMPLATE.iterdir()) if p.is_file()}
    checksum = _hash(pdf)
    manifest = dict(template_version=TEMPLATE_VERSION, pdf_sha256=checksum,
        input_sha256=_hash(_json(data)), workspace_id=data['workspace_id'], client_id=data['client_id'],
        reference_sha256=REFERENCE_SHA256, template_files=template_files, font_sha256=fonts,
        images=image_evidence, proposed_fee=data['proposed_fee'], commercial_model=data['commercial_model'],
        release_authorised=False, validation=dict(page_count=2, paragraph_boxes=measured,
            product_terms=True, internal_notice_each_page=True, distinct_images=True))
    return RenderedFieldworkProposal(pdf, checksum, TEMPLATE_VERSION, manifest)

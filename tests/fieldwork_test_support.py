"""Explicit PDF fixture for lifecycle tests on CI hosts lacking licensed Mac fonts.

These tests exercise workflow contracts, not rendering. Mac hosts still use the
real renderer. Dedicated renderer tests never use this fixture.
"""
import hashlib
from pathlib import Path
from unittest.mock import patch
from runtime.fieldwork_proposal import (
    TEMPLATE, TEMPLATE_VERSION, RenderedFieldworkProposal,
    render_fieldwork_proposal as actual_renderer,
)


def contract_test_renderer(data, **kwargs):
    if Path('/System/Library/Fonts/Supplemental/Baskerville.ttc').is_file():
        return actual_renderer(data, **kwargs)
    pdf = (TEMPLATE/'reference.pdf').read_bytes()
    return RenderedFieldworkProposal(pdf, hashlib.sha256(pdf).hexdigest(), TEMPLATE_VERSION,
        {'synthetic_test_fixture': True, 'validation': {'page_count': 2}})


def lifecycle_pdf_fixture(cls):
    return patch('runtime.fieldwork_proposal.render_fieldwork_proposal', new=contract_test_renderer)(cls)

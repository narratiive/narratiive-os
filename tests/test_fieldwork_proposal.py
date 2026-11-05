from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader

from runtime.fieldwork_proposal import (
    TEMPLATE, FONT_FILES, FieldworkProposalError, render_fieldwork_proposal, validate_inputs,
)


class FieldworkProposalTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((TEMPLATE / 'origin-fictional.json').read_text())

    def test_complete_input_and_exact_provisional_fee_required(self):
        validate_inputs(self.data)
        for change in (
            lambda d: d['copy'].pop('headline'),
            lambda d: d['proposed_fee'].update(approved=True),
            lambda d: d['proposed_fee'].update(amount='NaN'),
            lambda d: d['copy'].update(delivery_duration='10 days'),
            lambda d: d['copy'].update(headline='Growth Sprint'),
            lambda d: d['copy'].update(headline='<font size="80">Oops</font>'),
            lambda d: d['copy'].update(review_status='APPROVED'),
            lambda d: d['commercial_model'].update(ramp=[.5, float('nan'), .8]),
            lambda d: d['images']['origin-service-editorial-v4.png'].update(provenance=''),
        ):
            data = deepcopy(self.data)
            change(data)
            with self.assertRaises(FieldworkProposalError):
                validate_inputs(data)

    def test_asset_escape_duplicates_and_missing_fonts_fail_closed(self):
        data = deepcopy(self.data)
        data['images']['origin-service-editorial-v4.png']['path'] = '../reference.pdf'
        with self.assertRaises(FieldworkProposalError):
            render_fieldwork_proposal(data, asset_root=TEMPLATE)
        data = deepcopy(self.data)
        data['images']['origin-service-editorial-v4.png']['path'] = data['images']['origin-audience-editorial-v4.png']['path']
        with self.assertRaisesRegex(FieldworkProposalError, 'distinct'):
            render_fieldwork_proposal(data, asset_root=TEMPLATE)
        with tempfile.TemporaryDirectory() as fonts:
            with self.assertRaisesRegex(FieldworkProposalError, 'font unavailable'):
                render_fieldwork_proposal(self.data, asset_root=TEMPLATE, font_dir=Path(fonts))

    @unittest.skipUnless(all((Path('/System/Library/Fonts/Supplemental')/f).is_file() for f in FONT_FILES.values()), 'Approved Mac fonts unavailable; no substitute permitted')
    def test_reproducible_two_page_candidate_and_changed_fee_model(self):
        first = render_fieldwork_proposal(self.data, asset_root=TEMPLATE)
        self.assertEqual(first.pdf, render_fieldwork_proposal(self.data, asset_root=TEMPLATE).pdf)
        reader = PdfReader(io.BytesIO(first.pdf))
        self.assertEqual(len(reader.pages), 2)
        self.assertTrue(all('FICTIONAL / INTERNAL REVIEW' in p.extract_text() for p in reader.pages))
        self.assertFalse(first.manifest['release_authorised'])
        self.assertFalse(first.manifest['proposed_fee']['approved'])
        self.data['proposed_fee']['amount'] = '8400'
        self.data['commercial_model']['accounts'] = [6, 10, 14]
        changed = render_fieldwork_proposal(self.data, asset_root=TEMPLATE)
        text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(changed.pdf)).pages)
        self.assertIn('£8,400 ex VAT', text)
        self.assertIn('+£99k', text)
        self.assertNotIn('£9,800', text)
        self.assertNotEqual(first.checksum, changed.checksum)

    @unittest.skipUnless(all((Path('/System/Library/Fonts/Supplemental')/f).is_file() for f in FONT_FILES.values()), 'Approved Mac fonts unavailable; no substitute permitted')
    def test_overflow_rejected_without_silent_shrink(self):
        self.data['copy']['headline'] = 'An extremely long headline ' * 20
        with self.assertRaisesRegex(FieldworkProposalError, 'exceeds approved box'):
            render_fieldwork_proposal(self.data, asset_root=TEMPLATE)


if __name__ == '__main__':
    unittest.main()

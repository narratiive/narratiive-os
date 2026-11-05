#!/usr/bin/env python3
"""Render one internal Fieldwork candidate into a new, immutable output folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime.fieldwork_proposal import render_fieldwork_proposal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--font-dir', type=Path, default=Path('/System/Library/Fonts/Supplemental'))
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing paths are rejected')
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = render_fieldwork_proposal(data, asset_root=args.asset_root, font_dir=args.font_dir)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'proposal.pdf').write_bytes(result.pdf)
    (args.output / 'input.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    (args.output / 'manifest.json').write_text(json.dumps(result.manifest, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(pdf=str((args.output/'proposal.pdf').resolve()), sha256=result.checksum, template_version=result.template_version)))


if __name__ == '__main__':
    main()

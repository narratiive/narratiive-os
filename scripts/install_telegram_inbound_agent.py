from __future__ import annotations

import json
from pathlib import Path


LABEL = "com.narratiive.telegram-inbound"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            {
                "status": "deprecated",
                "label": LABEL,
                "message": (
                    "Narratiive's standalone Telegram getUpdates poller is retired. "
                    "OpenClaw now owns Telegram inbound and routes the default Telegram account directly to Tony."
                ),
                "next_command": f"{root / '.venv' / 'bin' / 'python'} {root / 'scripts' / 'install_openclaw_fleet.py'} --apply",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

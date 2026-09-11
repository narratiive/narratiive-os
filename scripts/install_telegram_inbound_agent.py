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
                    "The published n8n Telegram Trigger owns inbound and routes it through Tony's authenticated bridge."
                ),
                "next_command": f"See {root / 'docs' / 'operations' / 'TELEGRAM_INBOUND.md'} for the n8n ingress installer command.",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

"""Export live internal effect-authoring metadata as stable JSON.

This developer utility deliberately imports the registry rather than carrying
its own effect table.  It is not a Host API surface.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
import sys


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from light_engine.effects import list_effect_registrations  # noqa: E402


def authoring_contract() -> dict[str, object]:
    """Return a JSON-safe snapshot derived entirely from the live registry."""

    effects = []
    for registration in list_effect_registrations():
        effects.append(
            {
                "id": registration.id,
                "display_name": registration.capability.display_name,
                "common_params": list(registration.capability.common_params),
                "common_controls": sorted(registration.capability.common_controls),
                "color_source_support": registration.color_source_support,
                "parameters": [asdict(spec) for spec in registration.parameter_specs],
            }
        )
    return {"schema_version": 1, "effects": effects}


def main() -> int:
    json.dump(authoring_contract(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

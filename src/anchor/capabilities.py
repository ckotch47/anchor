from __future__ import annotations

from typing import Any

from anchor import __version__
from anchor.contract_registry import OPERATION_REGISTRY


def capability_snapshot() -> dict[str, Any]:
    """Return the versioned, transport-neutral public contract snapshot."""

    return {
        "contract_version": "1.0",
        "anchor_version": __version__,
        "surfaces": {
            surface: {
                operation_name: {
                    "scope": spec.scope,
                    "transports": list(spec.transports),
                    "parameters": [
                        {"name": item.name, "required": item.required, "type": item.type}
                        for item in spec.parameters
                    ],
                }
                for operation_name, spec in operations.items()
            }
            for surface, operations in OPERATION_REGISTRY.items()
        },
    }

from __future__ import annotations

import secrets
import time
import uuid

_UUID7_VERSION = 0x7
_UUID7_VARIANT = 0b10
_UUID7_TIMESTAMP_BITS = 48
_UUID7_RANDOM_A_BITS = 12
_UUID7_RANDOM_B_BITS = 62


def uuid7_str() -> str:
    timestamp_ms = int(time.time_ns() // 1_000_000) & ((1 << _UUID7_TIMESTAMP_BITS) - 1)
    rand_a = secrets.randbits(_UUID7_RANDOM_A_BITS)
    rand_b = secrets.randbits(_UUID7_RANDOM_B_BITS)
    value = (
        (timestamp_ms << 80)
        | (_UUID7_VERSION << 76)
        | (rand_a << 64)
        | (_UUID7_VARIANT << 62)
        | rand_b
    )
    return str(uuid.UUID(int=value))


def is_uuid7_str(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return False
    return parsed.version == 7 and parsed.variant == uuid.RFC_4122


def ensure_uuid7_str(value: str, field: str = "id") -> str:
    if not value.strip():
        raise ValueError(f"{field} must not be empty")
    if not is_uuid7_str(value):
        raise ValueError(f"{field} must be a UUIDv7 value")
    return value

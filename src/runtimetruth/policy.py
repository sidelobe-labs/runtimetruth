"""Persisted verification policy loading."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class PolicyError(RuntimeError):
    """Raised when a verification policy cannot be loaded safely."""


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    """Versioned persisted selectors for RuntimeTruth verification."""

    version: int
    protect: tuple[str, ...]


def _deduplicate(selectors: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []

    for selector in selectors:
        if selector in seen:
            continue
        seen.add(selector)
        result.append(selector)

    return tuple(result)


def load_policy(path: str) -> VerificationPolicy:
    """Load one explicit schema-v1 verification policy from TOML."""
    policy_path = Path(path)

    try:
        payload = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PolicyError(f"could not read policy {path!r}: {exc.strerror}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"invalid policy {path!r}: {exc}") from exc

    allowed_keys = {"version", "protect"}
    unknown_keys = sorted(set(payload) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(repr(key) for key in unknown_keys)
        raise PolicyError(f"unsupported policy key(s): {joined}")

    version = payload.get("version")
    if type(version) is not int or version != 1:
        raise PolicyError("policy version must be integer 1")

    raw_protect = payload.get("protect")
    if not isinstance(raw_protect, list) or not raw_protect:
        raise PolicyError("policy protect must be a non-empty array of selectors")

    selectors: list[str] = []
    for index, value in enumerate(raw_protect):
        if not isinstance(value, str):
            raise PolicyError(f"policy protect[{index}] must be a string selector")

        selector = value.strip()
        if not selector:
            raise PolicyError(f"policy protect[{index}] must not be empty")

        selectors.append(selector)

    return VerificationPolicy(
        version=version,
        protect=_deduplicate(selectors),
    )

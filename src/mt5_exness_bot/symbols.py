from __future__ import annotations

# Longer suffixes first so "EURUSDmicro" is not stripped down to "EURUSDmicro" minus "m".
_SUFFIXES = ("micro", ".pro", "pro", ".raw", ".m", ".r", ".c", "m", "c", "r")


def symbol_candidates(logical: str) -> list[str]:
    """Exness symbol names to try for a logical name such as ``EURUSD``.

    Standard accounts usually list ``EURUSDm``. Cent accounts use ``EURUSDc``.
    Raw Spread and Zero accounts usually list the bare name.
    """
    cleaned = logical.strip().upper()
    if not cleaned:
        return []
    base = cleaned
    for suffix in _SUFFIXES:
        if cleaned.endswith(suffix.upper()):
            base = cleaned[: -len(suffix)]
            break
    ordered = [cleaned]
    for suffix in ("", *_SUFFIXES):
        candidate = f"{base}{suffix}"
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered

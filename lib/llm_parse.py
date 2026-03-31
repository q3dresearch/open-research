"""Utilities for normalizing LLM response fields.

LLMs return inconsistent types — a field might come back as:
  - str                   "floor_area_sqm"
  - list[str]             ["floor_area_sqm", "storey_median"]
  - list[dict]            [{"feature": "floor_area_sqm", "reason": "..."}]
  - dict                  {"feature": "floor_area_sqm"}
  - None / missing

These utilities convert any of those into a predictable Python type so
agents don't need per-field try/except or isinstance guards.
"""


def as_str_list(val, key: str = "feature") -> list[str]:
    """Convert any LLM list field to a flat list of strings.

    Args:
        val:  The raw field value from the LLM response dict.
        key:  If items are dicts, use this key to extract the string value.
              Falls back to str(item) if key not found.

    Examples:
        as_str_list(["a", "b"])                     → ["a", "b"]
        as_str_list([{"feature": "a"}, {"feature": "b"}])  → ["a", "b"]
        as_str_list("a")                            → ["a"]
        as_str_list(None)                           → []
    """
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, dict):
        return [str(val.get(key, val))]
    if isinstance(val, (list, tuple)):
        result = []
        for item in val:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.append(str(item.get(key, next(iter(item.values()), str(item)))))
            else:
                result.append(str(item))
        return result
    return [str(val)]


def as_str(val, fallback: str = "") -> str:
    """Convert any LLM scalar field to a plain string.

    Examples:
        as_str("clean")          → "clean"
        as_str(None)             → ""
        as_str({"value": "x"})  → "x"   (first dict value)
    """
    if val is None:
        return fallback
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Try common key names first
        for k in ("value", "name", "label", "text", "result"):
            if k in val:
                return str(val[k])
        # Fall back to first value
        first = next(iter(val.values()), fallback)
        return str(first)
    return str(val)


def as_dict(val, fallback: dict | None = None) -> dict:
    """Ensure LLM field is a dict, wrapping or defaulting as needed."""
    if val is None:
        return fallback if fallback is not None else {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            import json
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def join_list(val, key: str = "feature", sep: str = ", ") -> str:
    """Convert an LLM list field to a joined string for display.

    Convenience: as_str_list + sep.join.
    """
    return sep.join(as_str_list(val, key=key))

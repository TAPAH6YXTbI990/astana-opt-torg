from __future__ import annotations

import json
from urllib.parse import parse_qs


def split_form_key(key: str) -> list[str]:
    parts: list[str] = []
    chunk = ""
    i = 0
    while i < len(key):
        char = key[i]
        if char == "[":
            if chunk:
                parts.append(chunk)
                chunk = ""
            closing = key.find("]", i)
            if closing == -1:
                chunk = key[i + 1 :]
                break
            if closing > i + 1:
                parts.append(key[i + 1 : closing])
            i = closing
        elif char != "]":
            chunk += char
        i += 1
    if chunk:
        parts.append(chunk)
    return parts or [key]


def assign_nested(target: dict, path: list[str], value: object) -> None:
    current = target
    for part in path[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    current[path[-1]] = value


def load_payload(body: bytes, content_type: str) -> dict:
    if not body:
        return {}

    text = body.decode("utf-8", errors="replace")
    lowered = content_type.lower()
    if "json" in lowered:
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError:
            pass

    try:
        parsed = parse_qs(text, keep_blank_values=True)
        flattened: dict[str, object] = {}
        for key, values in parsed.items():
            value: object = values[0] if len(values) == 1 else values
            path = split_form_key(key)
            if len(path) > 1:
                assign_nested(flattened, path, value)
            else:
                flattened[key] = value
        return flattened
    except Exception:
        return {"raw": text}


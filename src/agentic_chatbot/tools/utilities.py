"""Local utility tools that need no external service or API key."""

import base64
import binascii
import hashlib
import json
import re
import secrets
import string
import uuid

from langchain_core.tools import tool

_LENGTH_TO_METERS = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "mi": 1609.344,
    "ft": 0.3048,
    "in": 0.0254,
    "yd": 0.9144,
}

_MASS_TO_KILOGRAMS = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "lb": 0.45359237,
    "oz": 0.028349523125,
}

_VOLUME_TO_LITERS = {
    "l": 1.0,
    "ml": 0.001,
    "gal": 3.785411784,
    "qt": 0.946352946,
}

_TEMPERATURE_UNITS = {"c", "f", "k"}


def _convert_temperature(value: float, source: str, target: str) -> float:
    if source == "c":
        celsius = value
    elif source == "f":
        celsius = (value - 32) * 5 / 9
    else:
        celsius = value - 273.15

    if target == "c":
        return celsius
    if target == "f":
        return celsius * 9 / 5 + 32
    return celsius + 273.15


@tool
def generate_uuid() -> str:
    """Generate a random RFC 4122 version 4 UUID."""
    return str(uuid.uuid4())


@tool
def generate_password(length: int = 16, use_symbols: bool = True) -> str:
    """Generate a strong random password.

    Length must be between 8 and 128. Set use_symbols to False for an
    alphanumeric-only password.
    """
    if not 8 <= length <= 128:
        return "Error: length must be between 8 and 128."

    alphabet = string.ascii_letters + string.digits
    if use_symbols:
        alphabet += "!@#$%^&*()-_=+[]{};:,.?"

    return "".join(secrets.choice(alphabet) for _ in range(length))


@tool
def hash_text(text: str, algorithm: str = "sha256") -> str:
    """Hash text and return the hex digest.

    Supported algorithms: sha256, sha512, sha1, md5.
    """
    supported = {"sha256", "sha512", "sha1", "md5"}
    algorithm = algorithm.strip().lower()

    if algorithm not in supported:
        return f"Error: unsupported algorithm '{algorithm}'."

    return hashlib.new(algorithm, text.encode("utf-8")).hexdigest()


@tool
def base64_encode(text: str) -> str:
    """Encode UTF-8 text as a Base64 string."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@tool
def base64_decode(text: str) -> str:
    """Decode a Base64 string back into UTF-8 text."""
    try:
        return base64.b64decode(text, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as error:
        return f"Error: {error}"


@tool
def format_json(raw_json: str) -> str:
    """Validate a JSON string and return it pretty-printed with 2-space indentation."""
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as error:
        return f"Error: {error}"

    return json.dumps(parsed, indent=2, ensure_ascii=False)


@tool
def regex_search(pattern: str, text: str, max_results: int = 10) -> str:
    """Find all matches of a regular expression in text.

    Returns a JSON array of matches with their text, offsets, and groups.
    """
    try:
        matches = list(re.finditer(pattern, text))
    except re.error as error:
        return f"Error: {error}"

    limit = max(1, min(max_results, 100))
    payload = [
        {
            "match": match.group(0),
            "start": match.start(),
            "end": match.end(),
            "groups": list(match.groups()),
        }
        for match in matches[:limit]
    ]

    return json.dumps(payload, indent=2, ensure_ascii=False)


@tool
def summarize_text(text: str, max_sentences: int = 3) -> str:
    """Create a short extractive summary by keeping the first N sentences."""
    if not text.strip():
        return "Error: text is empty."

    limit = max(1, min(max_sentences, 10))
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    summary = " ".join(sentences[:limit])

    return summary


@tool
def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common length, mass, volume, and temperature units.

    Length: m, km, cm, mm, mi, ft, in, yd.
    Mass: kg, g, mg, lb, oz.
    Volume: l, ml, gal, qt.
    Temperature: c, f, k.
    """
    source = from_unit.strip().lower()
    target = to_unit.strip().lower()

    if source in _TEMPERATURE_UNITS or target in _TEMPERATURE_UNITS:
        if source not in _TEMPERATURE_UNITS or target not in _TEMPERATURE_UNITS:
            return "Error: both units must be temperature units."
        converted = _convert_temperature(value, source, target)
        return f"{converted:.6g} {target}"

    for table in (_LENGTH_TO_METERS, _MASS_TO_KILOGRAMS, _VOLUME_TO_LITERS):
        if source in table and target in table:
            converted = value * table[source] / table[target]
            return f"{converted:.6g} {target}"

    return f"Error: cannot convert '{source}' to '{target}'."

"""The JSON Schema is shared with the TypeScript consumer; no duplicate enums."""
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "contracts.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
Draft202012Validator.check_schema(SCHEMA)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def bytes_digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(kind, value):
    # Also reject NaN/Infinity, which are not JSON and differ between validators.
    try:
        canonical(value)
    except TypeError as error:
        raise ValueError(f"{kind}: input contains a non-JSON value: {error}") from error
    validator = Draft202012Validator({"$ref": f"#/$defs/{kind}", "$defs": SCHEMA["$defs"]})
    errors = sorted(validator.iter_errors(value), key=lambda e: str(list(e.absolute_path)))
    if errors:
        error = errors[0]
        where = "/".join(map(str, error.absolute_path)) or "$"
        raise ValueError(f"{kind}/{where}: {error.message}")
    return value


def read_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Invalid JSON: {x}")))

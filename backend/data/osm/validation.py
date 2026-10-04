"""Artifact validation does not imply source or real-world completeness."""

import json
from datetime import datetime
from pathlib import Path

from data.osm.contracts import Part, checksum


def timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return Part.aware(result)
    except ValueError:
        return None


def read_response(raw: bytes, *, require_header=True) -> dict:
    def no_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        payload = json.loads(raw, parse_constant=no_constant, object_pairs_hook=unique_object)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid raw response JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Expected a response object with an elements array")
    if require_header:
        if payload.get("version") != 0.6 or not isinstance(payload.get("generator"), str) or not payload["generator"]:
            raise ValueError("Missing Overpass source header")
        header = payload.get("osm3s")
        if not isinstance(header, dict) or timestamp(header.get("timestamp_osm_base")) is None:
            raise ValueError("Missing source_base_timestamp")
    return payload


def artifact_path(root: Path, reference: str) -> Path:
    root = root.resolve()
    path = (root / reference).resolve()
    if Path(reference).is_absolute() or not path.is_relative_to(root):
        raise ValueError("Artifact reference must stay inside artifact root")
    return path


def validate_part(part: Part, root: Path) -> tuple[dict, bytes]:
    if part.collection_status != "SUCCESS" or part.error or part.remark:
        raise ValueError("Failed/partial part or reported error/remark")
    if part.http_status != 200 or not part.artifact_reference or not part.artifact_checksum:
        raise ValueError("Missing successful response/artifact metadata")
    raw = artifact_path(root, part.artifact_reference).read_bytes()
    if checksum(raw) != part.artifact_checksum:
        raise ValueError("Artifact checksum mismatch")
    payload = read_response(raw)
    if payload.get("remark") or payload.get("error"):
        raise ValueError("Overpass response has a remark/error")
    if part.element_count != len(payload["elements"]):
        raise ValueError("Element count mismatch")
    if timestamp(payload["osm3s"]["timestamp_osm_base"]) != part.source_base_timestamp:
        raise ValueError("Source base timestamp mismatch")
    return payload, raw

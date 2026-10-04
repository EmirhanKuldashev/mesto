"""Future opt-in collection; responses and exact queries are write-once artifacts."""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from data.osm.contracts import BUILDER_VERSION, Extent, Manifest, Part, canonical_bytes, checksum
from data.osm.query import load_definition, query_hash, render_query
from data.osm.validation import read_response, timestamp

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def overpass_request(query: str) -> tuple[int, bytes]:
    """Single explicit POST; no retries, background refresh or import-time I/O."""
    request = Request(OVERPASS_URL, data=urlencode({"data": query}).encode(), method="POST",
        headers={"User-Agent": "MESTO/0.1 (https://github.com/EmirhanKuldashev/mesto)"})
    try:
        with urlopen(request, timeout=90) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def collect(*, dataset_id: str, scope_id: str, snapshot_id: str, extent: Extent,
            parts: dict[str, Extent], output_dir: Path, requested_as_of: datetime | None = None,
            transport: Callable[[str], tuple[int, bytes]] = overpass_request,
            clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Manifest:
    definition = load_definition()
    # Validate all configuration before side effects/network calls.
    for part_id, bbox in parts.items():
        Part(part_id=part_id, extent=bbox, collection_status="UNKNOWN")
    Manifest(dataset_id=dataset_id, scope_id=scope_id, snapshot_id=snapshot_id,
        extent=extent, query_definition=definition, query_version=definition.query_version,
        query_hash=query_hash(definition, extent, requested_as_of), requested_as_of=requested_as_of,
        parts=tuple(Part(part_id=key, extent=value, collection_status="UNKNOWN") for key, value in parts.items()))
    output_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for part_id, bbox in sorted(parts.items()):
        query = render_query(definition, bbox, requested_as_of)
        request_reference = f"{part_id}.query.txt"
        with (output_dir / request_reference).open("x", encoding="utf-8", newline="") as stream:
            stream.write(query)
        status, raw, error, remark, base, count = None, None, None, None, None, None
        try:
            status, raw = transport(query)
            if not isinstance(raw, bytes):
                raise ValueError("Transport must return immutable bytes")
        except (OSError, ValueError) as exc:
            error = f"{type(exc).__name__}: collection request failed"
        fetched_at = Part.aware(clock())
        reference = None
        digest = None
        if raw is not None:
            reference = f"{part_id}.response.json"
            with (output_dir / reference).open("xb") as stream:
                stream.write(raw)
            digest = checksum(raw)
            try:
                parsed = read_response(raw)
                base = timestamp(parsed["osm3s"]["timestamp_osm_base"])
                count = len(parsed["elements"])
                remark = str(parsed["remark"]) if parsed.get("remark") else None
                error = str(parsed["error"]) if parsed.get("error") else error
            except ValueError as exc:
                error = str(exc)
        successful = status == 200 and raw is not None and not error and not remark
        records.append(Part(part_id=part_id, extent=bbox, query_text=query,
            query_hash=query_hash(definition, bbox, requested_as_of), request_reference=request_reference,
            artifact_reference=reference, artifact_checksum=digest, source_base_timestamp=base,
            fetched_at=fetched_at, collection_status="SUCCESS" if successful else "FAILED",
            http_status=status, element_count=count, remark=remark, error=error))
    manifest = Manifest(dataset_id=dataset_id, scope_id=scope_id, snapshot_id=snapshot_id,
        extent=extent, query_definition=definition, query_version=definition.query_version,
        query_hash=query_hash(definition, extent, requested_as_of), requested_as_of=requested_as_of,
        parts=tuple(records), builder_version=BUILDER_VERSION)
    with (output_dir / "manifest.json").open("xb") as stream:
        stream.write(canonical_bytes(manifest.model_dump(mode="json")))
    return manifest

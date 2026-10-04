"""Tracked query definition plus deterministic request rendering."""

from datetime import datetime, timezone
from pathlib import Path

from data.osm.contracts import Extent, QueryDefinition, canonical_bytes, checksum


def load_definition() -> QueryDefinition:
    return QueryDefinition.model_validate_json(Path(__file__).with_name("query.json").read_bytes())


def render_query(definition: QueryDefinition, extent: Extent, requested_as_of: datetime | None = None) -> str:
    def number(value):
        return repr(value)
    bbox = ",".join(number(v) for v in (extent.south, extent.west, extent.north, extent.east))
    date = ""
    if requested_as_of is not None:
        if requested_as_of.utcoffset() is None:
            raise ValueError("requested_as_of must include a timezone")
        date = f'[date:"{requested_as_of.astimezone(timezone.utc).isoformat()}"]'
    lines = []
    for selector in sorted(definition.selectors, key=lambda s: s.key):
        values = sorted(selector.values)
        expression = f'="{values[0]}"' if len(values) == 1 else f'~"^({"|".join(values)})$"'
        lines.append(f'  nwr["{selector.key}"{expression}]({bbox});')
    return f'[out:json][timeout:{definition.timeout_seconds}]{date};(\n' + "\n".join(lines) + f'\n);out {definition.output_mode};'


def query_hash(definition: QueryDefinition, extent: Extent, requested_as_of: datetime | None = None) -> str:
    return checksum(canonical_bytes({"query_version": definition.query_version,
        "source": definition.source, "query_text": render_query(definition, extent, requested_as_of)}))

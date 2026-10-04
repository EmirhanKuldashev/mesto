"""Offline-only validation/build entry point. Collection is an explicit API."""

import argparse
from pathlib import Path

from data.osm.builder import build
from data.osm.contracts import Manifest, Status, canonical_bytes


def main():
    parser = argparse.ArgumentParser(description="Offline OSM manifest validation/build; no network")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = Manifest.model_validate_json(args.manifest.read_bytes())
    result = build(manifest, args.artifact_root or args.manifest.parent)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, value in (("canonical.json", result.canonical),
                        ("build-report.json", {**result.report, "canonical_checksum": result.canonical_checksum})):
        with (args.output_dir / name).open("xb") as stream:
            stream.write(canonical_bytes(value))
    print(result.quality.quality_status, result.canonical_checksum)
    raise SystemExit(0 if result.quality.quality_status == Status.VALIDATED else 2)


if __name__ == "__main__":
    main()

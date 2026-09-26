"""Only allow a successful push CI run for the exact commit to reach production."""

import json
import sys
from urllib.request import Request, urlopen


def main() -> int:
    sha = sys.argv[1]
    url = (
        "https://api.github.com/repos/EmirhanKuldashev/mesto/actions/"
        f"workflows/ci.yml/runs?head_sha={sha}&event=push&per_page=5"
    )
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "mesto-production-deployer",
    })
    with urlopen(request, timeout=15) as response:
        runs = json.load(response)["workflow_runs"]
    return 0 if any(
        run["head_sha"] == sha and run["status"] == "completed"
        and run["conclusion"] == "success" for run in runs
    ) else 1


if __name__ == "__main__":
    sys.exit(main())

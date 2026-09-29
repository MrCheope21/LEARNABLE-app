"""Writes the API's OpenAPI schema to a file (docs/WEB_ARCHITECTURE.md §3).

    python scripts/export_openapi.py ../web/openapi.json

The web client generates its TypeScript types from this file, and web CI regenerates it to fail
on drift, so the browser client is always typed against the real API rather than a copy.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The schema doesn't depend on configuration, but importing the app loads the settings, which
# require a signing secret. A placeholder is fine: nothing is signed here.
os.environ.setdefault("AUTH_SECRET", "openapi-export-only-" + "x" * 32)

from app.main import app


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    schema = app.openapi()
    Path(sys.argv[1]).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

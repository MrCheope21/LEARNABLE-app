"""Seeds a deterministic demo account for trying the app end to end (docs/DEVELOPMENT.md).

    cd backend
    AI_PROVIDER=mock .venv/bin/python -m alembic upgrade head
    AI_PROVIDER=mock .venv/bin/python scripts/seed_demo.py

Creates (once; running it again changes nothing) the user below, with one Course, one Chapter,
one study document filed under it, and the Chapter's curriculum applied. Every Concept is left
NOT_STUDIED, so the app flow starts where a real user would: open a Concept and activate it.

Goes through the real API in-process (FastAPI's TestClient against the configured database),
so the data is exactly what the app would create. Needs AI_PROVIDER=mock: the demo must not
depend on (or spend money on) a real model.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

# A throwaway local demo account, printed on purpose; never create it on a real deployment.
EMAIL = "demo@example.com"
PASSWORD = "learnable-demo-2026"  # noqa: S105
COURSE = "Diritto bancario (demo)"
CHAPTER = "Contratti bancari"
MATERIAL = """# Il deposito bancario

Il deposito bancario e il contratto con cui la banca acquista la proprieta del denaro depositato. \
Il depositante ha diritto alla restituzione della somma alla scadenza o a richiesta.

# L'apertura di credito

L'apertura di credito e il contratto con cui la banca si obbliga a tenere a disposizione del \
cliente una somma di denaro per un certo periodo. Il cliente puo utilizzarla in piu volte.
"""


def main() -> int:
    if get_settings().ai_provider != "mock":
        print("Set AI_PROVIDER=mock: the demo must not call a real model.", file=sys.stderr)
        return 1
    api = "/api/v1"
    with TestClient(app) as client:
        credentials = {"email": EMAIL, "password": PASSWORD}
        client.post(f"{api}/auth/register", json=credentials)  # 409 if it exists: fine
        login = client.post(f"{api}/auth/login", json=credentials)
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        courses = client.get(f"{api}/courses", headers=headers).json()
        if any(c["title"] == COURSE for c in courses):
            print(f"Already seeded: {EMAIL} / {PASSWORD}")
            return 0

        course = client.post(
            f"{api}/courses", json={"title": COURSE, "language": "it"}, headers=headers
        ).json()
        chapter = client.post(
            f"{api}/courses/{course['id']}/chapters", json={"title": CHAPTER}, headers=headers
        ).json()
        upload = client.post(
            f"{api}/courses/{course['id']}/documents",
            files={"file": ("contratti-bancari.md", MATERIAL.encode(), "text/markdown")},
            data={"chapter_id": chapter["id"]},
            headers=headers,
        )
        upload.raise_for_status()
        # TestClient runs background tasks before returning: processing and generation are done.
        proposal = client.post(
            f"{api}/courses/{course['id']}/curriculum-proposals",
            json={"chapter_id": chapter["id"]},
            headers=headers,
        ).json()
        proposal_url = f"{api}/curriculum-proposals/{proposal['id']}"
        proposal = client.get(proposal_url, headers=headers).json()
        if proposal["status"] != "READY":
            print(f"Curriculum generation ended {proposal['status']}", file=sys.stderr)
            return 1
        body = {
            "topics": [
                {
                    "title": topic["title"],
                    "concepts": [
                        {
                            "title": concept["title"],
                            "source_chunk_ids": [s["chunk_id"] for s in concept["sources"]],
                        }
                        for concept in topic["concepts"]
                    ],
                }
                for topic in proposal["topics"]
            ]
        }
        applied = client.post(
            f"{api}/curriculum-proposals/{proposal['id']}/apply", json=body, headers=headers
        )
        applied.raise_for_status()
    print(f"Seeded {COURSE!r}. Sign in with {EMAIL} / {PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

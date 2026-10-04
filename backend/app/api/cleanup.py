"""After a request that deleted questions: remove the drawing files their rows took with them."""

import uuid

from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_session_factory
from app.services import drawings
from app.storage.documents import DocumentStorage, get_document_storage


class DrawingCleanup:
    """A route dependency: `cleanup.after(course_id)` sweeps that course once the response is
    sent (services/drawings.py `sweep`), on its own session."""

    def __init__(
        self,
        background: BackgroundTasks,
        session_factory: sessionmaker[Session] = Depends(get_session_factory),
        storage: DocumentStorage = Depends(get_document_storage),
    ) -> None:
        self._background = background
        self._session_factory = session_factory
        self._storage = storage

    def after(self, course_id: uuid.UUID) -> None:
        self._background.add_task(
            drawings.sweep_job, self._session_factory, self._storage, course_id
        )

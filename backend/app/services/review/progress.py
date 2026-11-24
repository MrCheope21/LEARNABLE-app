"""How far an item has got inside a session: answered well, and how many times.

"Well" means graded GOOD or EASY. HARD (correct, with difficulty) is a pass for the schedule but
not "well", and neither is AGAIN. Repeats (answers that only decide another answer's grade) are
never counted.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ReviewOutcome
from app.models.review import Answer

GOOD_OUTCOMES = (ReviewOutcome.GOOD, ReviewOutcome.EASY)
# First study: an item is consolidated after this many good answers, in a row or not.
GOOD_ANSWERS_NEEDED = 3
# A failed review comes back in the same session until it is answered well. Past this many
# attempts the session lets it go (it stays due at level 0 for the next one).
MAX_RELEARN_ATTEMPTS = 6


def is_good(outcome: ReviewOutcome | None) -> bool:
    return outcome in GOOD_OUTCOMES


def good_answers(db: Session, session_id: uuid.UUID, item_id: uuid.UUID) -> int:
    # The answer just graded is still only in the session: write it, or it isn't counted.
    db.flush()
    return int(
        db.scalar(
            select(func.count())
            .select_from(Answer)
            .where(
                Answer.session_id == session_id,
                Answer.learning_item_id == item_id,
                Answer.repeat_of_id.is_(None),
                Answer.final_outcome.in_(GOOD_OUTCOMES),
            )
        )
        or 0
    )


def attempts(db: Session, session_id: uuid.UUID, item_id: uuid.UUID) -> int:
    db.flush()
    return int(
        db.scalar(
            select(func.count())
            .select_from(Answer)
            .where(
                Answer.session_id == session_id,
                Answer.learning_item_id == item_id,
                Answer.repeat_of_id.is_(None),
            )
        )
        or 0
    )

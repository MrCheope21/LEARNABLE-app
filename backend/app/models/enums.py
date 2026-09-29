from enum import StrEnum


class StudyState(StrEnum):
    """docs/PROJECT_SPEC.md §22 — does NOT represent memory strength."""

    NOT_STUDIED = "NOT_STUDIED"
    STUDIED = "STUDIED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"


class DocumentKind(StrEnum):
    """File types the Knowledge Repository accepts (docs/PROJECT_SPEC.md §16)."""

    PDF = "PDF"
    TEXT = "TEXT"
    MARKDOWN = "MARKDOWN"
    DOCX = "DOCX"
    PPTX = "PPTX"
    IMAGE = "IMAGE"


class DocumentStatus(StrEnum):
    """Ingestion pipeline state (docs/PROJECT_SPEC.md §17). FAILED documents stay stored, with a
    user-safe reason, so nothing the user uploaded silently disappears."""

    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class DocumentPurpose(StrEnum):
    """What an upload is. MATERIAL is study material the AI builds a curriculum from; a
    QUESTION_BANK holds the user's own labelled questions and expected answers, imported as they
    are, without AI."""

    MATERIAL = "MATERIAL"
    QUESTION_BANK = "QUESTION_BANK"


class CurriculumProposalStatus(StrEnum):
    """AI curriculum proposal lifecycle (docs/PROJECT_SPEC.md §20). Nothing reaches the Course
    until the user applies a READY proposal."""

    GENERATING = "GENERATING"
    READY = "READY"
    # The material had nothing to build a curriculum from (spec §19); not an error.
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    FAILED = "FAILED"
    APPLIED = "APPLIED"


# --- Learning and review (Phases 8, 10-12) ---


class LearningItemRole(StrEnum):
    """What a Learning Item is for (docs/PROJECT_SPEC.md §24). The AI suggests a role; whether
    the item is actually trained is the separate, user-controlled `in_training` flag."""

    CORE_TRAINABLE = "CORE_TRAINABLE"
    SUPPORTING_TRAINABLE = "SUPPORTING_TRAINABLE"
    COMMON_TRAP = "COMMON_TRAP"
    INFORMATIONAL = "INFORMATIONAL"
    REFERENCE = "REFERENCE"
    OPTIONAL_EXTENSION = "OPTIONAL_EXTENSION"


# Roles that go into training by default when generated.
TRAINABLE_ROLES = frozenset(
    {
        LearningItemRole.CORE_TRAINABLE,
        LearningItemRole.SUPPORTING_TRAINABLE,
        LearningItemRole.COMMON_TRAP,
    }
)


class QuestionType(StrEnum):
    """docs/PROJECT_SPEC.md §28."""

    RECALL = "RECALL"
    DEFINITION = "DEFINITION"
    EXPLANATION = "EXPLANATION"
    WHY_HOW = "WHY_HOW"
    COMPARISON = "COMPARISON"
    CAUSE_EFFECT = "CAUSE_EFFECT"
    APPLICATION = "APPLICATION"
    SCENARIO = "SCENARIO"
    CALCULATION = "CALCULATION"
    CLASSIFICATION = "CLASSIFICATION"
    TEACH_BACK = "TEACH_BACK"
    ORAL_EXAM = "ORAL_EXAM"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    EDGE_CASE = "EDGE_CASE"
    CONCEPT_CONNECTION = "CONCEPT_CONNECTION"


class MemoryState(StrEnum):
    """Memory state of a Learning Item (docs/PROJECT_SPEC.md §23). Owned by the
    SchedulingPolicy; never the Concept's."""

    NEW = "NEW"  # not encoded yet: waits for a LEARN session
    LEARNING = "LEARNING"  # encoded, early levels
    REVIEW = "REVIEW"
    RELEARNING = "RELEARNING"  # failed after having been learned (a lapse)
    MASTERED = "MASTERED"  # at the top level of the ladder


class ReviewOutcome(StrEnum):
    """docs/PROJECT_SPEC.md §46. Decided by the ReviewOutcomeResolver (or the user's override),
    never by the AI directly."""

    AGAIN = "AGAIN"
    HARD = "HARD"
    GOOD = "GOOD"
    EASY = "EASY"


class SessionIntent(StrEnum):
    """What a session is for, pedagogically. Decides whether answers touch the schedule."""

    LEARN = "LEARN"  # introduce newly activated items and encode them
    SCHEDULED_REVIEW = "SCHEDULED_REVIEW"  # due items; drives the SchedulingPolicy
    PRACTICE = "PRACTICE"  # deliberate practice; does not change SRS state by default
    EXAM = "EXAM"  # no feedback during the session (Phase 15)
    # "I have studied this concept": each selected NEW item is asked three times in a row, with
    # feedback after each round. One encoding transition after the last round
    # (docs/SCHEDULING.md §4a).
    CONSOLIDATION = "CONSOLIDATION"


class SelectionMode(StrEnum):
    """How a session's pool is chosen (docs/PROJECT_SPEC.md §49), independent of intent."""

    DUE = "DUE"
    NEW = "NEW"
    COURSE_ORDER = "COURSE_ORDER"
    RANDOM = "RANDOM"
    WEAK = "WEAK"
    RECENTLY_FAILED = "RECENTLY_FAILED"
    MARKED_HARD = "MARKED_HARD"
    SELECTED = "SELECTED"
    # CONSOLIDATION: the concept's NEW items, each in three consecutive slots.
    CONSOLIDATION = "CONSOLIDATION"


class EvaluationClassification(StrEnum):
    """docs/PROJECT_SPEC.md §38."""

    CORRECT = "CORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    MISCONCEPTION = "MISCONCEPTION"
    WRONG = "WRONG"
    UNCERTAIN = "UNCERTAIN"


class ItemGenerationStatus(StrEnum):
    """Learning Item generation for one Concept (background job, like curriculum proposals)."""

    NONE = "NONE"
    GENERATING = "GENERATING"
    READY = "READY"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    FAILED = "FAILED"


class AnswerMethod(StrEnum):
    TEXT = "TEXT"
    VOICE = "VOICE"  # the transcript is the text; audio is not stored (spec §84)


class EvaluationStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"  # the provider was unavailable or answered invalid output
    NOT_CONFIGURED = "NOT_CONFIGURED"  # AI_PROVIDER is empty: the user grades themselves


class XpReason(StrEnum):
    """Why an attempt was (or wasn't) worth XP (docs/XP_AND_ACTIVITY.md)."""

    INITIAL = "INITIAL"  # one of an item's first three consolidation rounds
    SCHEDULED_REVIEW = "SCHEDULED_REVIEW"  # a review of an item that was due

"""Key-respondent helpers (port of lib/respondents.ts)."""

DOCUMENT_REVIEW_RESPONDENT = "Document review"


def is_document_review(value: str) -> bool:
    return str(value or "").strip().lower() == DOCUMENT_REVIEW_RESPONDENT.lower()

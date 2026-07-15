import hashlib

from app.repositories.interviews import FeedbackReportRecord

PRACTICE_STATUS_PENDING = "pending"
PRACTICE_STATUS_PRACTICED = "practiced"
PRACTICE_STATUS_IMPROVING = "improving"
PRACTICE_STATUS_NEEDS_WORK = "needs_work"


def weakness_key(value: str) -> str:
    normalized = "".join(value.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def classify_practice_status(weakness: str, report: FeedbackReportRecord) -> str:
    repeated = _weakness_repeated(weakness, report.weaknesses)
    if report.score < 60:
        return PRACTICE_STATUS_NEEDS_WORK
    if repeated and report.score < 75:
        return PRACTICE_STATUS_NEEDS_WORK
    if report.score >= 80 and not repeated:
        return PRACTICE_STATUS_PRACTICED
    return PRACTICE_STATUS_IMPROVING


def _weakness_repeated(weakness: str, report_weaknesses: list[str]) -> bool:
    target = _compact(weakness)
    if not target:
        return False
    for item in report_weaknesses:
        text = _compact(item)
        if text and (target in text or text in target):
            return True
    return False


def _compact(value: str) -> str:
    return "".join(value.strip().lower().split())

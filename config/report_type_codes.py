from __future__ import annotations


REPORT_TYPE_CODES = {
    "company_report",
    "issue_comment",
    "industry_report",
    "technical_report",
    "ai_company_report",
    "unknown",
}


def normalize_report_type(raw_type: str | None, title: str | None = None) -> str:
    text = f"{raw_type or ''} {title or ''}".replace(" ", "").casefold()
    if not text:
        return "unknown"
    if "ai기업분석" in text or "ai_company" in text or "kirs_ai" in text:
        return "ai_company_report"
    if "기술분석" in text or "technical" in text or "kirs_tech" in text:
        return "technical_report"
    if "산업분석" in text or "산업리포트" in text or "industry" in text:
        return "industry_report"
    if "이슈분석" in text or "이슈코멘트" in text or "issue" in text:
        return "issue_comment"
    if (
        "기업분석" in text
        or "기업리포트" in text
        or "company" in text
        or "kirs_research" in text
    ):
        return "company_report"
    return "unknown"

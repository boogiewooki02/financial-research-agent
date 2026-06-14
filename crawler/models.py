from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ReportMetadata:
    """크롤러에서 수집해 저장 파이프라인으로 전달하는 리포트 DTO."""

    # 리포트를 식별하는 고유 ID. 예: kirs-2246
    report_id: str

    # 리포트 제목
    title: str = ""

    # 리포트 작성자 또는 작성기관
    securities_firm: str = ""

    # 리포트 게시일. YYYY-MM-DD 형식
    published_date: str = ""

    # 수집원 또는 리포트 분류. 예: KIRS_RESEARCH, KIRS_AI
    report_type: str = ""

    # 상장기업의 6자리 종목코드 (예: 005930). 비상장 리포트는 빈 문자열
    stock_code: str = ""

    # 분석 대상 기업명
    company_name: str = ""

    # 리포트가 발견된 목록 페이지 URL
    source_url: str = ""

    # PDF 원문 다운로드 URL. PDF가 없으면 빈 문자열
    pdf_url: str = ""


@dataclass
class DownloadResult:
    """PDF 다운로드 단계가 파이프라인에 반환하는 결과 DTO."""

    # 검증을 마친 임시 PDF 파일 경로. 최종 저장 전에는 .pdf.part 확장자를 사용
    temp_path: str

    # 다운로드한 PDF 전체 내용의 SHA-256 해시
    pdf_hash: str

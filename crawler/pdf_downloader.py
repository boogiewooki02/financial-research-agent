from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import httpx

from crawler.config import Settings
from crawler.http import create_ssl_context
from crawler.models import DownloadResult

logger = logging.getLogger(__name__)


class PdfDownloadError(RuntimeError):
    pass


class PdfDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(
            headers={"User-Agent": settings.user_agent},
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            verify=create_ssl_context(),
        )

    def close(self) -> None:
        self.client.close()

    def download_to_temp(self, pdf_url: str, final_path: Path) -> DownloadResult:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.with_suffix(".pdf.part")
        last_error: Exception | None = None

        for attempt in range(1, self.settings.download_retries + 1):
            try:
                result = self._download_once(pdf_url, temp_path)
                time.sleep(self.settings.request_delay_seconds)
                return result
            except Exception as exc:
                last_error = exc
                temp_path.unlink(missing_ok=True)
                logger.warning(
                    "PDF 다운로드 실패 (%s/%s): %s - %s",
                    attempt,
                    self.settings.download_retries,
                    pdf_url,
                    exc,
                )
                if attempt < self.settings.download_retries:
                    time.sleep(min(2 ** (attempt - 1), 5))

        raise PdfDownloadError(str(last_error) if last_error else "알 수 없는 다운로드 오류")

    def _download_once(self, pdf_url: str, temp_path: Path) -> DownloadResult:
        digest = hashlib.sha256()
        first_bytes = b""
        file_size = 0

        with self.client.stream("GET", pdf_url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()

            with temp_path.open("wb") as output:
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(first_bytes) < 5:
                        first_bytes += chunk[: 5 - len(first_bytes)]
                    digest.update(chunk)
                    file_size += len(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())

        valid_pdf = is_pdf_content(content_type, first_bytes)
        if not valid_pdf:
            temp_path.unlink(missing_ok=True)
            raise PdfDownloadError(
                f"PDF 검증 실패: content_type={content_type or '없음'} signature={first_bytes!r}"
            )

        return DownloadResult(
            temp_path=str(temp_path),
            pdf_hash=digest.hexdigest(),
            file_size=file_size,
            content_type=content_type,
            is_valid_pdf=valid_pdf,
        )

    @staticmethod
    def commit(temp_path: str, final_path: Path) -> None:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        Path(temp_path).replace(final_path)


def is_pdf_content(content_type: str, first_bytes: bytes) -> bool:
    return "application/pdf" in content_type.lower() or first_bytes.startswith(b"%PDF")


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

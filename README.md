# 기업 리서치 PDF 수집 파이프라인

한국IR협의회(KIRS) 기업리서치센터의 공개 목록에서 리포트 메타데이터와 PDF 원문을 수집해 SQLite와 로컬 파일 시스템에 저장하는 MVP입니다. 아직 PDF 텍스트 추출, 청킹, 임베딩 및 Vector DB 저장 과정은 포함하지 않습니다.

## 기본 수집원

기본값은 기업리서치센터가 직접 작성한 리서치 보고서입니다.

- 기본: `https://www.kirs.or.kr/research/research22_1.html`
- 아웃소싱: `https://www.kirs.or.kr/research/research.html`
- 기술분석: `https://www.kirs.or.kr/information/tech2020_1.html`
- AI 기업분석: `https://www.kirs.or.kr/research/ai_report.html`

수집원을 바꿀 때는 `KIRS_RESEARCH_URL`과 `REPORT_TYPE`을 함께 설정합니다.
각 페이지는 동일한 표 구조를 사용하며 AI 보고서의 `data-url` 방식도 지원합니다.

## 처리 흐름

1. httpx로 robots.txt와 리서치 목록 페이지를 조회합니다.
2. BeautifulSoup으로 종목명, 종목코드, 제목, 작성자·기관, 등록일과 PDF URL을 파싱합니다.
3. SQLite에서 `pdf_url` 중복을 확인합니다.
4. PDF를 임시 파일에 내려받아 Content-Type과 PDF 시그니처를 검증합니다.
5. SHA-256 해시 중복을 확인한 뒤 날짜별 경로로 원자적으로 이동합니다.
6. 리포트 상태와 실행 단위 통계를 SQLite 및 로그에 기록합니다.

## 구조

```text
.
├── crawler/
│   ├── config.py
│   ├── models.py
│   ├── kirs_research_crawler.py
│   ├── pdf_downloader.py
│   ├── pipeline.py
│   └── scheduler.py
├── db/
│   ├── database.py
│   └── schema.sql
├── storage/raw_pdfs/
├── logs/
├── tests/
├── main.py
└── requirements.txt
```

## 설치

Python 3.11 이상을 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

프로젝트 루트의 `.env` 파일을 자동으로 읽습니다. 예제 파일을 복사한 뒤 필요한
값을 수정합니다.

```bash
cp .env.example .env
```

`.env`는 `.gitignore`에 포함되어 Git에 커밋되지 않습니다. 셸, Docker, CI에
같은 환경변수가 이미 설정되어 있으면 해당 값이 `.env`보다 우선합니다.

## 수집원 변경

`.env`에서 인소싱 리서치 설정:

```dotenv
KIRS_RESEARCH_URL=https://www.kirs.or.kr/research/research22_1.html
REPORT_TYPE=KIRS_RESEARCH
```

아웃소싱 리서치:

```dotenv
KIRS_RESEARCH_URL=https://www.kirs.or.kr/research/research.html
REPORT_TYPE=KIRS_OUTSOURCED
```

기술분석 보고서:

```dotenv
KIRS_RESEARCH_URL=https://www.kirs.or.kr/information/tech2020_1.html
REPORT_TYPE=KIRS_TECH
```

AI 기업분석 보고서:

```dotenv
KIRS_RESEARCH_URL=https://www.kirs.or.kr/research/ai_report.html
REPORT_TYPE=KIRS_AI
```

## DB 초기화

```bash
python main.py --init-db
```

기본 DB 경로는 `db/reports.db`이며 실행 시에도 스키마가 자동 생성됩니다.

`reports` 테이블 상태:

- `DISCOVERED`: 메타데이터 발견, PDF 링크가 없거나 다운로드 전
- `DOWNLOADED`: PDF 저장 완료
- `DUPLICATED`: 기존 `pdf_url` 또는 SHA-256 해시와 중복
- `FAILED`: 다운로드 또는 검증 실패

기존 스키마 호환을 위해 KIRS의 `작성자` 또는 `작성기관` 값은 `securities_firm` 필드에 저장합니다. `collection_runs`에는 실행별 시작·종료 시각과 발견, 다운로드, 중복, 실패 건수가 저장됩니다.

## 실행

한 번 실행:

```bash
python main.py --run-once
```

매일 스케줄 실행:

```bash
python main.py --schedule
```

기본 스케줄은 `Asia/Seoul` 기준 매일 오전 7시입니다.

```dotenv
SCHEDULE_HOUR=7
SCHEDULE_MINUTE=0
SCHEDULE_TIMEZONE=Asia/Seoul
```

설정 후 `python main.py --schedule`을 실행합니다.

운영 환경에서는 systemd, Docker, Supervisor 또는 Kubernetes CronJob 같은 프로세스 관리 수단과 함께 사용해야 합니다.

## 저장 데이터

PDF:

```text
storage/raw_pdfs/{year}/{month}/{day}/{report_id}.pdf
```

SQLite `reports`:

```text
report_id, title, securities_firm, published_date, report_type,
stock_code, company_name, source_url, pdf_url, pdf_path, pdf_hash,
collected_at, status, error_message
```

로그는 콘솔과 `logs/crawler.log`에 기록됩니다.

## 테스트

```bash
python -m unittest discover -v
```


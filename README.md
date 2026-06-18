# Agent B 데이터 수집 인프라

AI Agent 기반 증권 리포트 분석 서비스에서 Agent B는 공통 데이터 인프라와 데이터 수집을 담당합니다. 리포트 목록, 표준 메타데이터, PDF 원본 파일 경로, 목표주가/투자의견, 주가 데이터, 매크로 데이터를 SQLite와 로컬 파일 시스템에 저장합니다.

## 지원 기업

수집 대상은 7개 기업으로 제한합니다. 내부 매칭 기준은 `ticker`이며, alias 기반 resolver는 `config/supported_companies.py`에 있습니다.

```text
005930 삼성전자
000660 SK하이닉스
005380 현대차
035420 NAVER
003230 삼양식품
352820 HYBE
373220 LG에너지솔루션
```

## 설치

Python 3.11 이상을 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 환경 설정

프로젝트 루트의 `.env`를 자동으로 읽습니다. 셸, Docker, CI에 같은 환경변수가 있으면 해당 값이 우선합니다.

```dotenv
CRAWLER_SOURCE=naver
COLLECTION_MONTHS=1
MAX_PAGES=3
MAX_REPORTS_PER_COMPANY=10
MAX_TOTAL_REPORTS=50

REQUEST_TIMEOUT=20
REQUEST_INTERVAL_SECONDS=1.5
MAX_RETRIES=3

PRICE_DATA_PROVIDER=naver
MACRO_DATA_PROVIDER=naver
INCLUDE_PRICE_DATA=false
INCLUDE_MACRO_DATA=false

CRAWLER_SCHEDULE_HOUR=7
CRAWLER_SCHEDULE_MINUTE=0
SCHEDULE_TIMEZONE=Asia/Seoul
```

로컬 MVP 기본값은 최근 1개월, 기업당 최대 10개, 전체 실행 최대 50개 리포트입니다. 운영 환경이나 클라우드 스토리지를 사용할 때는 `COLLECTION_MONTHS=3` 또는 `COLLECTION_MONTHS=6`처럼 확장할 수 있습니다.

## 실행

DB 초기화:

```bash
python main.py --init-db
```

수동 실행:

```bash
python main.py --run-once --source naver
python main.py --run-once --source kirs
python main.py --run-once --source all
```

옵션 포함 실행:

```bash
python main.py --run-once --source naver --months 6 --max-pages 3 --include-price-data --include-macro-data
```

스케줄 실행:

```bash
python main.py --schedule
```

APScheduler가 `.env`의 `CRAWLER_SCHEDULE_HOUR`, `CRAWLER_SCHEDULE_MINUTE`, `SCHEDULE_TIMEZONE`에 따라 매일 실행합니다.

## 처리 흐름

1. `crawler_runs`에 실행 시작 기록
2. 지원 기업 7개 목록 로드
3. source별 리포트 목록 수집
4. company/ticker 매칭 및 report type 정규화
5. 재현 가능한 `report_id` 생성
6. `report_metadata` 저장
7. 목표주가/투자의견이 있으면 `target_price_data` 저장
8. `pdf_url` 중복 검사
9. PDF 다운로드, Content-Type/시그니처 검증, SHA-256 계산
10. SHA-256 중복 검사
11. `report_files` 저장 및 `report_metadata.status` 갱신
12. 옵션에 따라 실제 provider의 주가/매크로 데이터 저장
13. `crawler_runs`에 실행 결과 저장

## 저장 구조

PDF 원본은 DB에 직접 저장하지 않고 파일 시스템에 저장합니다.

```text
storage/raw_report_pdfs/{source}/{year}/{month}/{day}/{report_id}.pdf
```

DB에는 `file_path`만 저장합니다. PDF 원본은 내부 처리와 추적용이며 서비스 화면에서 직접 재배포하지 않는 전제입니다.

## DB 스키마

SQLite 테이블:

- `report_metadata`: 리포트 표준 메타데이터와 수집 상태
- `report_files`: PDF 파일 경로, URL, SHA-256, Content-Type, 유효성
- `target_price_data`: HTML에서 명시적으로 확인 가능한 목표주가/투자의견
- `price_data`: Naver Finance 또는 선택 provider 기반 주가 데이터
- `macro_data`: Naver 시장지표 또는 선택 provider 기반 매크로 데이터
- `crawler_runs`: 실행 단위 집계와 실패 사유

상태값:

```text
discovered, success, failed, duplicate, no_pdf_url
```

## 중복 처리

중복은 두 단계로 확인합니다.

1. `pdf_url`이 `report_metadata` 또는 `report_files`에 이미 성공/중복 상태로 존재하면 다운로드하지 않고 `duplicate`
2. 다운로드 후 계산한 `sha256`이 이미 존재하면 임시 파일을 삭제하고 `duplicate`

중복 건은 `crawler_runs.duplicate_count`에 반영됩니다.

## Report Type

`normalize_report_type(raw_type, title)`은 다음 코드로 정규화합니다.

```text
company_report
issue_comment
industry_report
technical_report
ai_company_report
unknown
```

## 수치 데이터 Provider

기본값은 실제 수집 provider입니다.

- `PRICE_DATA_PROVIDER=naver`: Naver Finance 일별 시세를 수집해 `price_data`에 저장
- `MACRO_DATA_PROVIDER=naver`: Naver 시장지표에서 USD/KRW를 수집해 `macro_data`에 저장

실제 수치 데이터까지 포함해 실행:

```bash
python main.py --run-once --source naver --include-price-data --include-macro-data
```

네트워크가 없는 테스트 환경에서는 `.env`에서 `PRICE_DATA_PROVIDER=mock`,
`MACRO_DATA_PROVIDER=mock`으로 바꿀 수 있습니다. 추후 한국투자 Open API, ECOS API 구현체로 교체할 수 있도록 `collectors/`에 provider 경계를 두었습니다.

## 로그

콘솔과 `logs/crawler.log`에 다음을 기록합니다.

- 수집 시작/종료와 source
- 기업별 발견 리포트 수
- 총 발견 리포트 수
- 다운로드 성공, 중복, 실패 수
- target/price/macro 저장 수
- 실패 사유와 PDF 저장 경로

## 테스트

```bash
python -m unittest discover -v
```

테스트 범위는 company resolver, report type 정규화, report_id 생성, SHA-256/PDF 검증, 중복 검사, target price 저장 조건, price/macro provider 파서를 포함합니다.

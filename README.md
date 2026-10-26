# 법원경매 데이터 수집기

법원경매 부동산을 조건으로 찾고, 상세를 확인하고, 수집한 자료를 Excel·CSV·JSONL로 저장합니다. **SIONLAB 제작 · MIT · Python 3.11+ · v0.2.1**

유료 AI·API 키·Supabase·개인 작업 환경 없이 CLI와 Python으로 실행할 수 있습니다. 원하는 지역을 선택해 데이터를 수집하고 파일로 받을 수 있습니다.

```mermaid
flowchart LR
    A[조건 정하기] --> B[물건 가져오기] --> C[상세 확인] --> D[엑셀 저장]
```

> 법원 사이트 내부 JSON 요청을 쓰는 **비공식 연동**입니다. 사이트 변경·점검·차단으로 멈출 수 있습니다. [공식 이용안내](https://openapi.scourt.go.kr/kgso202m01.do)는 2026-10-26 확인 시 일반 오픈API를 추후 제공 예정으로 안내합니다. 실제 입찰 전 법원 원문을 다시 확인하세요.

## 설치

[GitHub 릴리스](https://github.com/solid-hwan/court-auction-mcp/releases/tag/v0.2.1)의 ZIP과 SHA-256 파일을 받아 해시를 확인하고 압축을 풉니다. PyPI 배포는 하지 않습니다.

```bash
cd court-auction-mcp-0.2.1
python3 setup-lab.py
.venv/bin/python -m court_auction_mcp coverage
.venv/bin/court-auction-mcp codes
```

Windows에서는 `python setup-lab.py`와 `.venv\Scripts\python.exe -m court_auction_mcp coverage`를 사용합니다. 설치는 제품 폴더의 `.venv`에 한정됩니다. Linux에 `ensurepip`가 없고 기존 `uv`가 있으면 이를 사용합니다. 둘 다 없으면 Python의 venv 지원 환경이 필요합니다. Windows 실실행은 검증하지 않았습니다.

기존 가상환경에는 `python -m pip install -r requirements.lock` 뒤 `python -m pip install --no-build-isolation --no-deps .`로 설치할 수 있습니다.

## 지역을 선택해서 받기

**v0.2.0부터 지역 선택 실행기와 지역별 폴더 저장을 제공합니다.**

설치 후 `python 지역별/지역선택.py`를 실행하면 시·도와 시·군·구 목록에서 번호를 고르고 매각기일을 입력할 수 있습니다. 결과는 `지역별/수집결과/작업폴더/`에 저장됩니다. Python 설치와 최초 패키지 설치는 필요하며 별도 API 키는 필요하지 않습니다. [지역별 사용 안내](지역별/README.md)를 참고하세요.

```bash
python 지역별/지역선택.py
# 또는 가상환경 실행 파일로
.venv/bin/python -m court_auction_mcp guide
# JSON 파일 없이 조건 직접 입력
court-auction-mcp codes --region 서울
court-auction-mcp collect --job-id gangnam-nov --region 서울 --district 11680 --start 2026-11-01 --end 2026-11-30
court-auction-mcp export --job-id gangnam-nov
```

`guide`는 기본 한도 10회 안에서 지역 코드 조회와 수집을 진행합니다. 기본 1페이지이며 `--max-pages 2`로 늘릴 수 있습니다. 재개는 표시된 작업 ID로 `collect --job-id ID`를 실행합니다. 시·군·구 목록은 공식 사이트에서 조회하므로 연결·차단 상태에 영향을 받습니다. 전국 시도 목록은 오프라인으로 볼 수 있습니다.

## 먼저 가상 자료로 연습하기

```bash
.venv/bin/python examples/run_example.py
```

외부 요청 없이 가상 토지·건물 2개를 수집하고 세 형식 파일을 만든 뒤 Excel·CSV 원문 복원을 비교합니다. 출력 경로는 마지막 JSON에 표시됩니다. 실제 경매 데이터는 배포본에 없습니다.

## 실제 물건 검색과 상세

`examples/query.json`의 법원 또는 지역과 시작·종료일을 원하는 범위로 바꿉니다. 기본 페이지 크기는 10이며 기간은 매각기일 기준입니다.

```json
{
  "court": "B000210",
  "start": "2026-10-26",
  "end": "2026-11-30",
  "usage": "all",
  "page_size": 10
}
```

```bash
court-auction-mcp search --query examples/query.json
court-auction-mcp search --query examples/query.json --page 2
court-auction-mcp detail --court B000210 --case 2099타경123
```

마지막 사건번호는 **가상 예시**입니다. 실조회에서는 검색 결과의 `normalized.court_code`와 `normalized.case_no`를 사용하세요. `.venv/bin/` 경로를 생략하려면 가상환경을 활성화합니다. 모든 명령은 `python -m court_auction_mcp`로도 같습니다.

| 조건 | 입력 |
|---|---|
| 법원·지역 | `court`: 법원 코드 또는 유일하게 구분되는 이름, `region`: 시도 2자리 또는 이름, `district`: 시군구 5자리(시도와 함께) |
| 용도 | `usage`: `all`, `land`, `building`; 필요하면 `usage_mid`·`usage_small`에 공식 사이트의 5자리 코드 |
| 매각기일 | `start`, `end`: YYYY-MM-DD, 양 끝 포함 |
| 감정가 | `appraisal_min`, `appraisal_max`: 원 단위 정수 |
| 최저매각가 | `minimum_min`, `minimum_max`: 원 단위 정수 |
| 유찰 횟수 | `failures_min`, `failures_max`: 0 이상 정수 |

`codes`는 법원 60곳, 시도 17곳, 토지·건물 대분류를 제공합니다. `codes --region 서울`처럼 시도를 지정하면 공식 시군구 목록을 조회합니다. 세부 용도 목록의 동적 조회는 제공하지 않습니다. 법원과 지역은 서로 다른 검색 방식이므로 동시에 지정하지 않습니다.

**용도 검색은 매각물건 기준이며, 함께 매각되는 토지와 건물 목적물이 모두 반환될 수 있습니다.** 건물 검색에 연결된 토지가 나와도 삭제하지 않습니다. 개별 목적물의 `property_kind`와 매각물건의 `usage`를 구분하세요. 같은 사건의 토지·건물 행에 가격이 반복될 수 있으므로 목적물별 가격을 단순 합산하지 마세요.

## 수집·중단 후 재개·Excel 저장

```bash
court-auction-mcp collect --job-id seoul-oct --query examples/query.json --max-pages 3
court-auction-mcp status --job-id seoul-oct
court-auction-mcp collect --job-id seoul-oct --max-pages 3
court-auction-mcp export --job-id seoul-oct --name seoul-oct-export
```

기본 작업 DB는 `~/.court-auction-mcp/jobs.sqlite3`, 출력은 현재 폴더의 `output/`입니다. 전역 옵션 `--db`와 `--export-root`는 명령 앞에 둡니다. 예: `court-auction-mcp --db ./jobs.sqlite3 --export-root ./exports status --job-id seoul-oct`.

- HTTP 요청은 같은 DB를 쓰는 실행들 사이에서 순차 처리하고 최소 3초 간격을 둡니다. 여러 DB·프로세스를 나눠 병렬 수집하지 마세요.
- 신규 작업의 기본 한도는 **초기 연결·재시도 포함 누적 10회**입니다. 재개해도 초기화되지 않습니다. 세션 쿠키는 저장하지 않아 재개할 때 초기 연결 1회가 다시 필요합니다.
- 필요하면 `collect --job-id seoul-oct --max-calls 15 --max-pages 2`처럼 **누적 한도**를 명시적으로 늘립니다. 같은 작업의 검색 조건은 바꿀 수 없습니다.
- 기본 `max-pages`는 1입니다. `status=partial`, `reason=page_limit`는 요청한 페이지 수에서 멈춘 상태입니다. `call_limit`는 누적 호출 한도입니다. 남은 위치는 `next_page`입니다.
- 차단·CAPTCHA·`ipcheck=false`·403/429는 즉시 멈추고 같은 DB에서 이후 요청도 막습니다. IP·브라우저·새 DB로 우회하지 마세요. 자동 차단 해제 기능은 없습니다.
- 5xx·일시적 네트워크 오류만 최대 한 번 재시도합니다. 점검·형식 변경·식별자 불일치·반복 페이지는 별도 상태로 보존합니다.
- `complete`는 관측한 페이지 끝에 도달했다는 뜻입니다. 실시간 원본의 누락 없는 스냅샷을 보장하지 않습니다. 전체 건수가 변하면 `source_changed`와 `partial=true`로 남깁니다.

출력에는 `records.xlsx`, 보기용 `overview.csv`, 복원용 `records.csv`, `records.jsonl`, `manifest.json`과 `지역별/` 폴더가 포함됩니다. `지역별/지역목록.csv`에서 원하는 지역 폴더를 찾으세요. 각 지역 폴더에도 Excel·CSV·JSONL이 저장됩니다. 기존 출력 폴더는 덮어쓰지 않습니다. Excel의 `Overview`에는 지역·주소·용도와 조건검증 상태, 자동 필터·행 고정·숫자 가격 열이 있으며, `records`·`long_values`는 복원용, `Collection`은 수집 범위·완료 여부입니다. 빈 금액은 0이 아니며 원문과 누락 이유를 함께 확인하세요. 긴 CSV를 Python으로 읽을 때는 기본 필드 길이 제한이 있으므로 아래 복원 함수를 사용합니다.

```python
from court_auction_mcp.export import restore_excel, restore_csv
records = list(restore_excel("output/seoul-oct-export/records.xlsx"))
assert records == list(restore_csv("output/seoul-oct-export/records.csv"))
```

`filter_mismatch_*`는 반환된 지역·날짜·가격·유찰 조건이 요청과 달라 해당 페이지를 저장하지 않고 중단했다는 뜻입니다. 누락값은 `filter_check.unverified`와 작업 `unverified_count`로 표시합니다. 용도는 연결 목적물만으로 확정할 수 없어 미확인으로 남깁니다. 수정 전 수집한 지역 작업은 그대로 이어 붙이지 않고 새 작업 ID로 다시 시작해야 합니다.

CLI 종료 코드: 정상 `0`, 입력·단일 요청 오류 `2`, 수집 미완료·중단 `3`입니다. 오류 메시지에 사이트 원문·쿠키를 포함하지 않습니다.

## Python과 MCP

```python
from court_auction_mcp import AuctionService
api = AuctionService(db="jobs.sqlite3", export_root="exports")
print(api.call("coverage"))
# api.call("search", {"query": {...}})
# api.call("collect", {"job_id": "sample", "query": {...}, "max_pages": 2})
```

`api.call()`은 CLI·MCP와 같은 오류 JSON을 반환합니다. `api.search()` 등 직접 메서드는 잘못된 입력에 `AuctionError`를 발생시킬 수 있습니다.

[examples/mcp-config.json](examples/mcp-config.json)을 참고해 사용하는 MCP 클라이언트에 직접 연결합니다. `command`에는 가상환경의 실행 파일 절대 경로를 쓰면 됩니다. 이 패키지는 운영 MCP 설정을 변경하지 않습니다.

| CLI | MCP |
|---|---|
| `codes` | `auction_codes` |
| `search` | `auction_search` |
| `detail` | `auction_detail` |
| `collect` | `auction_collect` |
| `status` | `auction_job_status` |
| `export` | `auction_export` |
| `coverage` | `auction_coverage` |

`serve`는 MCP stdio 서버를 실행합니다. MCP 수집 결과는 요약이며 대량 자료는 `auction_export`로 제공합니다. MCP 응답은 1MiB로 제한됩니다. 검색 페이지를 줄이거나 파일 출력을 사용하세요.

## 검증과 범위

[실제 검증](docs/verification.md) · [데이터 계약](docs/data-contract.md) · [기술 흐름](docs/architecture.md) · [출처·이용 조건](NOTICE.md) · [기여하기](CONTRIBUTING.md)

서울중앙지방법원·2026-10-26~2026-11-30 범위에서 검색 10건, 상세 1건, 두 페이지 20건 저장, 조건 검색 10건을 확인했습니다. 호출은 초기 연결 포함 총 9회였습니다. 이는 전국 법원·모든 상세 조합·전체 수집 완료를 검증한 결과가 아닙니다. v0.2.0에서는 서울 강남구 두 페이지 20건, 경기 성남시 분당구 10건의 지역·기간을 추가 대조했습니다. 전국 전체 지역을 실조회한 것은 아닙니다. 자세한 검증 상태는 `coverage`를 확인하세요.

사진·첨부문서 다운로드, 15B, 자동차·중기, 온비드, 권리분석·투자추천·입찰 자동화는 지원하지 않습니다. 누락값은 추정하지 않습니다. 관계인 이름·연락처와 인증값을 저장하지 않도록 필드를 제한하며, 코드 MIT 라이선스와 법원 원자료의 이용 조건은 별개입니다.

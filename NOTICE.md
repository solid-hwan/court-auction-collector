# 출처와 이용 조건

Copyright (c) 2026 SIONLAB. 이 패키지 코드는 MIT 라이선스입니다.

사용자 소유의 다음 로컬 구현을 승인된 범위에서 참고·추출했습니다. 현재 파일 SHA-256, 기준 커밋과 미커밋 변경 여부는 [source-provenance.json](docs/source-provenance.json)에 기록했습니다. 원본 저장소를 실행 의존성으로 사용하지 않습니다.

| 구현 | 활용 | 공개 패키지의 변경 |
|---|---|---|
| kk_real_estate/src/market/court_common.py | 법원 60개 코드·검색 기본 요청 필드 추출, 사건번호·요청 구조 참고 | 정직한 제품 UA, 최소 3초, 제한 재시도, 누적 한도, 엄격 파싱·허용목록으로 재작성 |
| kk_real_estate/src/market/court_auction.py | 페이지 응답·수집 구조 참고 | 법원 포함 복합키, SQLite 원자 저장·중복 페이지 감지 |
| kk_real_estate/src/market/court_detail.py | 15A 목적물·기일 필드 대조 | 개인정보 제외, 식별자 대조, 가격·기일의 추정 연결 제거 |
| aution_Real_estate/supabase/functions/_shared/court-search.ts·court-detail.ts | 요청과 필드 교차 대조 | 전체 코드·실제 응답 fixture는 배포하지 않음 |
| SIONLAB 나라장터 데이터 MCP 0.5.0 | SQLite 재개·stdio·Excel 긴 JSON 복원·격리 설치 구조 참고 | 이 제품의 계약과 시험으로 독립 구현 |

자동차·사진·관계인·권리분석 코드와 회피 목적 헤더·재시도 방식은 가져오지 않았습니다. 새 구현에는 원본 프로젝트 환경 경로·인증값이 없습니다. 코드 출처 목록에 있는 프로젝트 이름은 의존성을 뜻하지 않습니다.

의존성은 httpx(BSD-3-Clause), httpcore(BSD-3-Clause), h11(MIT), anyio(MIT), idna(BSD-3-Clause), certifi(MPL-2.0), openpyxl(MIT), et-xmlfile(MIT), typing-extensions(PSF-2.0)입니다. 빌드 도구 setuptools(MIT)·wheel(MIT)을 사용합니다. ZIP은 라이브러리 바이너리를 재배포하지 않으며 설치 시 각 배포본의 라이선스가 함께 설치됩니다.

법원 사이트 원자료의 권리·이용 조건은 이 코드의 MIT 라이선스와 별개입니다. 이 도구가 원자료의 재배포 권한을 부여하지 않습니다. 비공식 내부 JSON 연동이며 법원 공식 오픈API가 아닙니다. [법원 이용안내](https://openapi.scourt.go.kr/kgso202m01.do)는 2026-10-26 확인 시 일반 오픈API를 추후 업데이트 예정으로 설명합니다. 실제 입찰 전 [대한민국법원 법원경매정보](https://www.courtauction.go.kr) 원문을 다시 확인하세요.

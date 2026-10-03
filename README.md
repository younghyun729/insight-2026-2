# insight-2026-2

1차 인사이콘 - 데이터 기반 유럽 시장 수익성 진단 및 공급 포트폴리오 재설계 (5팀)

## 폴더 구조

```
data/raw/         InsightStay_data.csv                 # 원본 (git 제외)
                  시설_분석용_대체본.csv                  # 시설 3컬럼 대체본 (git 제외)
data/processed/   InsightStay_data_cleaned.parquet     # 마스터 데이터 (git 제외)
deliverables/     InsightStay_data_cleaned.csv         # ★ 팀 공유용 최종 산출물
                  PREPROCESSING.md                     # ★ 전처리 명세
notebooks/        eda.ipynb · segmentation_2x3.ipynb · midstay_min_nights.ipynb
scripts/          build_master.py                      # 마스터 데이터 생성
                  verify_gmv.py                        # 거래액·숙박일수 추정 검증
reports/          EDA_REPORT.md                        # 전처리 요약 · EDA · 세그먼트
                  SEGMENTATION_2x3*.md · MIDSTAY_MIN_NIGHTS.md
```

원본 CSV와 parquet은 용량 문제(약 1GB)로 git에서 제외되어 있습니다. 새 환경에서는 `data/raw/InsightStay_data.csv`를 직접 복사해 두고 노트북을 처음부터 실행하면 `data/processed/`가 재생성됩니다. 노트북은 실행 위치와 무관하게 `README.md`가 있는 폴더를 프로젝트 루트로 잡아 경로를 맞춥니다.

## 분석 산출물

> **현재 기준은 2×3 세그멘테이션입니다** (`source == 0` · 최근 1년 리뷰 O/X × 최소 숙박 단기·중기·장기 → 1~6번 칸).
> **발표 전략 흐름:** ① 중기 매물(2·5번) 최소 숙박 하향 → ② 신규 매물 처방 → ③ 장기 숙소(3·6번) 타겟팅

### 문서 읽는 순서

| 순서 | 문서 | 여기서 얻는 것 |
|---|---|---|
| 1 | [`deliverables/PREPROCESSING.md`](deliverables/PREPROCESSING.md) | **전처리 명세.** 결측 · 이상치 · 로그 변환 · 추가된 컬럼(4장). 수치는 `scripts/build_master.py` 실행 결과에서 자동 생성 |
| 2 | [`reports/EDA_REPORT.md`](reports/EDA_REPORT.md) | **전처리 요약 → EDA → 세그먼트를 한 흐름으로.** `source == 0`만 쓰는 근거(3장) · 최근 1년 리뷰 수를 쓰는 근거(4장) · 최소 숙박 경계(5장) · 칸에서 전략으로(7장) |
| 3 | [`reports/SEGMENTATION_2x3.md`](reports/SEGMENTATION_2x3.md) | **2×3 세그멘테이션.** 1~6번 칸별 특징과 painpoint |
| 4 | [`reports/SEGMENTATION_2x3_VALIDATION.md`](reports/SEGMENTATION_2x3_VALIDATION.md) | **수치 검증.** 칸별 근거 강도 · 통합 모델 · 6칸 전체 검증 |
| 5 | [`reports/MIDSTAY_MIN_NIGHTS.md`](reports/MIDSTAY_MIN_NIGHTS.md) | **전략 ① 근거.** 중기 매물(2·5번)이 최소 숙박을 3박 이하로 줄여야 하는 이유 · 같은 호스트 안 비교 · 2번의 끊김 위험 · 기대 효과 범위 |

### 발표 준비 — [`presentation/`](presentation/)

| 문서 | 내용 |
|---|---|
| [`presentation/DRAFT.md`](presentation/DRAFT.md) | 세부 내용을 채운 발표 초안 (전략 ② · ③은 팀원 작성 자리) |
| [`presentation/figures/`](presentation/figures/) | 발표용 차트 12장 — `python presentation/make_figures.py`로 다시 생성 |

재현 노트북: [`notebooks/eda.ipynb`](notebooks/eda.ipynb) (원본 탐색) · [`notebooks/segmentation_2x3.ipynb`](notebooks/segmentation_2x3.ipynb) (2×3 분석과 검증) · [`notebooks/midstay_min_nights.ipynb`](notebooks/midstay_min_nights.ipynb) (중기 매물 최소 숙박)

### 마스터 데이터에서 2×3 분석에 쓰는 컬럼

| 컬럼 | 뜻 |
|---|---|
| `cell` | 2×3 칸 1~6 (`source == 0`만, `source == 1`은 빈 값) |
| `alert_target` | 진단 알림 대상 — 4·5번 중 기준선(편의시설 −12개 / 가격 1.7배 / 최소 숙박 5박+)에 하나라도 걸리는 매물 (93,525건) |
| `alert_amenity` · `alert_price` · `alert_minnights` | 기준선별 해당 여부 |
| `price_rel` · `amenity_rel` · `peer` | 동급(도시 × 방 타입 × 인원) 대비 가격 · 편의시설과 그 그룹 키 |
| `season_index` | 지역 계절성 지수 (1보다 크면 여름 휴양지) |
| `new_listing` | 호스트 경력 1년 미만 & 누적 리뷰 0 — 팔릴 기회가 없었던 신규 매물 |
| `occ_review` | 리뷰 기반 가동률 (달력 가동률 대신 사용) |

정의 전체는 [`PREPROCESSING.md`](deliverables/PREPROCESSING.md) 4장에 있습니다.

### 거래액 추정 검증

```bash
python scripts/verify_gmv.py
```

리뷰 수로 역산한 숙박일수 · 거래액이 가정(리뷰 작성률 · 평균 숙박일 · 상한)에 얼마나 민감한지, 달력 · 견적 가격과 맞는지 확인합니다. `source == 0` · 가격 보유 매물 기준이고, 설정은 파일 위쪽 상수에서 바꿉니다.

## 마스터 데이터 생성

```bash
python scripts/build_master.py
```

`deliverables/` 에 최종 CSV(841,626행 × 89열)와 명세서를, `data/processed/` 에 같은 내용의 parquet 을 만듭니다. `name`·`description` 두 텍스트 컬럼은 용량 때문에 빠져 있으니 필요하면 원본에서 `id` 기준으로 머지하세요.

## 과제 개요

InsightStay(유럽 공유 숙박 플랫폼)의 등록 숙소 데이터를 분석해, **공급 확보 → 노출 → 예약 전환 → 재방문** 흐름에서 문제/개선 가능성을 찾고 플랫폼 수익성을 높일 전략을 제안한다.

- 문제의 개수보다 하나를 짚더라도 확실한 개선 방안 제시
- 분석 근거와 기대 효과는 반드시 **수치**로 뒷받침
- 본사 정책 또는 도시·호스트 단위에서 현실적으로 실행 가능한 방안일 것

## 분석 시 반드시 고려할 비즈니스 규칙

- 플랫폼 수익은 **거래액 연동 수수료 15.5%**에서 발생. 예약 안 되는 숙소는 매출 0 + 노출/지원 리소스 소모하는 비용 요인.
- 핵심 지표는 숙소 수가 아니라 **숙소당 창출 수익 = 가동률 × 객단가**. 도시 규모 ≠ 수익성.
- 가격 인상이 항상 답은 아님 — 객단가와 가동률은 상충 관계. `minimum_nights` 같은 설정이 예약 전환에 미치는 영향도 고려.
- 도시마다 규제 환경이 다름 (예: 파리·바르셀로나·암스테르담 vs 리스본·아테네) — 도시별 규제 리스크·시장 성숙도 고려.
- 호스트는 단일 집단이 아님 — 개인 호스트(1채) vs 전문 사업자(다채) 행동 방식·수익 기여도 상이.

## 데이터셋 (`data/raw/InsightStay_data.csv`)

주요 컬럼 그룹 (전체 50개 컬럼):

| 구분 | 주요 컬럼 |
| --- | --- |
| 키·출처 | `country`, `region`, `id`, `source` |
| 호스트 식별·이력 | `host_id`, `hosts_time_as_user_years/months`, `hosts_time_as_host_years/months`, `host_location`, `host_is_superhost` |
| 위치·숙소 속성 | `neighbourhood_group_cleansed`, `property_type`, `room_type`, `accommodates`, `bathrooms`, `bedrooms`, `beds`, `amenities` |
| 가격 | `price`, `price_quote_checkin/checkout_date`, `price_quote_total_price`, `discount_type`, `list_price` |
| 숙박일 제약 | `minimum_nights`, `maximum_nights` |
| 예약 가능성 | `availability_30/60/90/365` |
| 리뷰·활동량 | `number_of_reviews*`, `first_review`, `last_review`, `review_scores_*`, `reviews_per_month` |
| 호스트 리스팅 수 | 같은 호스트의 `entire_homes` / `private_rooms` / `shared_rooms` 매물 수 |

## 일정

- 데이터셋 공개: 2026-09-21 (월)
- **발표 자료 마감: 2026-10-03 (토) 22:59** — 마감 후 페이지 잠금, 수정 불가 (적발 시 감점)
- 조별 질문 제출: 2026-10-04 (일) 23:59 (전 팀에게 질문 1개씩)
- 질문 답변 작성: 2026-10-05 (월) 17:00
- **최종 발표: 2026-10-05 (월) 18:30** — 팀당 발표 12분(초과 시 감점) + 질의응답 5분

## 발표 형식 제약

- **Notion, Jupyter Notebook only** — PPT, HTML, 외부 링크 삽입 불가 (노션 내 HTML 삽입도 불가)
- 교육 세션 범위를 벗어나는 개념·모델링 사용 불가

## 평가 기준 (심사위원 60% + 15·16기 40%)

데이터 30 / 논리성 20 / 창의성 20 / 실효성 20 / 전달력 10

## 팀 구성 (5팀)

오규원(팀장), 류시현, 손영현, 최영효, 박주현

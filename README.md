# insight-2026-2

1차 인사이콘 - 데이터 기반 유럽 시장 수익성 진단 및 공급 포트폴리오 재설계 (5팀)

`InsightStay_data.csv`는 용량 문제(약 1GB)로 git에서 제외되어 있습니다. 다른 노트북에서 작업하려면 해당 파일을 별도로 복사해오세요.

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

## 데이터셋 (`InsightStay_data.csv`)

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

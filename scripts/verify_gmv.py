# -*- coding: utf-8 -*-
"""
거래액·숙박일수 검증 코드
리뷰 수로 역산한 숙박일수 · 거래액이 가정(리뷰 작성률 · 평균 숙박일 · 상한)에 얼마나
민감한지, 달력 · 견적 가격과 맞는지 확인한다. 마스터 데이터
(data/processed/InsightStay_data_cleaned.parquet)를 읽는다.

    python scripts/verify_gmv.py

열 이름이 다르면 아래 COL 만 고치면 됩니다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "data/processed/InsightStay_data_cleaned.parquet")

# ───────────── 0. 설정 ─────────────
COL = dict(
    id='id',                          # 리스팅 고유 ID
    min_nights='minimum_nights',      # 최소 숙박일
    price='price',                    # 1박당 숙박비 견적가
    rev_ltm='number_of_reviews_ltm',  # 최근 12개월 리뷰 수
    avail='availability_365',         # 앞으로 365일 중 예약 가능 일수
    region='region',                  # 지역 이름
)
ONLY_SOURCE_0 = True             # source=0(새로 수집)만 사용. 엑셀과 같은 기준
EXCLUDE_NEW = False              # True면 첫 리뷰가 최근 1년 이내인 신규 숙소 제외
REVIEW_RATES = [0.3, 0.5, 0.7]   # 리뷰 작성률 가정
AVG_STAYS = [2, 3, 4, 5]         # 평균 숙박일 가정 (엑셀은 3박)
CAP = 0.7                        # 연 점유율 상한 (365일의 70%)
pd.set_option('display.width', 200); pd.set_option('display.float_format', '{:,.1f}'.format)
pd.set_option('display.max_columns', 20)

def to_num(v):
    """'$1,234.00' 같은 문자열 가격도 숫자로 변환"""
    if not pd.api.types.is_numeric_dtype(v):
        v = v.astype(str).str.replace(r'[^0-9.\-]', '', regex=True).replace('', np.nan)
    return pd.to_numeric(v, errors='coerce')

d = df.copy()
if ONLY_SOURCE_0 and 'source' in d.columns:
    d = d[pd.to_numeric(d['source'], errors='coerce') == 0]
if EXCLUDE_NEW and 'first_review' in d.columns:
    fr = pd.to_datetime(d['first_review'], errors='coerce')
    d = d[~(fr > fr.max() - pd.Timedelta(days=365))]
d[COL['price']] = to_num(d[COL['price']])
print(f'분석 대상 {len(d):,}개 (가격 결측 {d[COL["price"]].isna().sum():,}개는 제외됨)')
for k in ('min_nights', 'price', 'rev_ltm'):
    d[COL[k]] = pd.to_numeric(d[COL[k]], errors='coerce')
d = d.dropna(subset=[COL['min_nights'], COL['price']])
d['rev'] = d[COL['rev_ltm']].fillna(0)
d['seg'] = pd.cut(d[COL['min_nights']], [0, 3, 29, np.inf], labels=['단기(1~3)', '중기(4~29)', '장기(30+)'])
d['is_active'] = (d['rev'] > 0).astype(int)

def estimate(x, rr, stay):
    """리뷰 수 역산: 예약 수 = 리뷰 ÷ 리뷰율, 박수 = 예약 수 × max(최소숙박일, 평균숙박일), 상한 적용"""
    los = np.maximum(x[COL['min_nights']], stay)
    raw = x['rev'] / rr * los
    nights = np.minimum(raw, 365 * CAP)
    return nights, nights * x[COL['price']], raw > 365 * CAP

# ───────────── 1. 세그먼트 기본 현황 ─────────────
print('\n[1] 세그먼트별 숙소 수·활성률 (엑셀: 중기 활성 43,293 / 비활성 33,369, 단기 비활성 144,645)')
print(d.groupby('seg', observed=True).agg(숙소수=('rev', 'size'), 활성=('is_active', 'sum'),
      활성률=('is_active', 'mean'), 가격평균=(COL['price'], 'mean'), 가격중앙값=(COL['price'], 'median')))

# ───────────── 2. 엑셀 값 재현 (활성 단기, 3박 가정) ─────────────
print('\n[2] 엑셀 값 재현: 활성 단기 숙소, 평균 3박 가정 (엑셀: 50% → 98박 / 19,173, 중앙값 66박 / 11,088)')
a = d[d['is_active'] == 1]
rows = []
for rr in REVIEW_RATES:
    x = a[a['seg'] == '단기(1~3)']
    n, g, c = estimate(x, rr, 3)
    rows.append(dict(리뷰율=rr, 박수평균=n.mean(), 박수중앙값=n.median(), 거래액평균=g.mean(), 거래액중앙값=g.median(), 상한걸린비율=c.mean()))
print(pd.DataFrame(rows))

# ───────────── 3. 숙박일 가정에 따른 민감도 ─────────────
print('\n[3] 평균 숙박일 가정을 바꾸면 거래액이 얼마나 달라지는가 (리뷰율 50%, 활성 숙소 평균)')
rows = []
for stay in AVG_STAYS:
    for seg, x in a.groupby('seg', observed=True):
        n, g, c = estimate(x, 0.5, stay)
        rows.append(dict(평균숙박일=stay, 세그먼트=seg, 박수평균=n.mean(), 거래액평균=g.mean(),
                         거래액중앙값=g.median(), 상한걸린비율=c.mean()))
t = pd.DataFrame(rows)
print(t.pivot(index='평균숙박일', columns='세그먼트', values='거래액평균'))
print('\n상한(70%)에 걸린 숙소 비율 — 높을수록 숙박일 가정이 아니라 상한이 결과를 정함')
print(t.pivot(index='평균숙박일', columns='세그먼트', values='상한걸린비율'))

# ───────────── 4. 예약 1건당 숙박일: 계산에 실제로 쓰인 값 ─────────────
print('\n[4] 계산에 쓰인 예약 1건당 숙박일 = max(최소 숙박일, 3). 리뷰 수로 가중한 평균이 실제 영향력')
a = a.assign(los=np.maximum(a[COL['min_nights']], 3))
print(a.groupby('seg', observed=True).apply(lambda x: pd.Series(dict(
    최소숙박일_중앙값=x[COL['min_nights']].median(),
    숙박일_단순평균=x['los'].mean(),
    숙박일_리뷰가중평균=np.average(x['los'], weights=x['rev']),
    숙소당_연리뷰_평균=x['rev'].mean(), 숙소당_연리뷰_중앙값=x['rev'].median()))))
print('\n중기 숙소의 최소 숙박일 분포 (전환 대상이 4~7박에 몰려 있는지)')
m = d[d['seg'] == '중기(4~29)']
print(pd.crosstab(pd.cut(m[COL['min_nights']], [3, 4, 5, 7, 14, 29]), m['is_active'], margins=True))

# ───────────── 5. 중기→단기 전환 시 거래액: 엑셀 가정 점검 ─────────────
print('\n[5] 엑셀은 "전환된 중기 숙소 = 활성 단기 숙소 평균 거래액"으로 가정. 실제 활성 중기 숙소의 현재 거래액과 비교')
for seg in ['단기(1~3)', '중기(4~29)']:
    x = a[a['seg'] == seg]; n, g, _ = estimate(x, 0.5, 3)
    print(f'  {seg}: 박수 평균 {n.mean():,.0f} / 거래액 평균 {g.mean():,.0f} / 중앙값 {g.median():,.0f} / 1박가 평균 {x[COL["price"]].mean():,.0f}')
print('  → 중기 1박가가 단기와 크게 다르면 단기 평균 거래액을 그대로 쓰면 안 됨')

# ───────────── 6. 달력과 교차 검증 ─────────────
if COL['avail'] in d.columns:
    print('\n[6] 달력 교차 검증: 추정 박수가 막힌 날(365 − 예약가능일)보다 크면 과대 추정')
    x = a[a['seg'] == '단기(1~3)'].copy()
    x['blocked'] = 365 - pd.to_numeric(x[COL['avail']], errors='coerce')
    n, g, _ = estimate(x, 0.5, 3)
    n2 = np.minimum(n, x['blocked']); g2 = n2 * x[COL['price']]
    print(f'  막힌 날 중앙값 {x["blocked"].median():,.0f}일 / 추정 박수 > 막힌 날 비율 {(n > x["blocked"]).mean():.1%}')
    print(f'  거래액 평균: 원래 {g.mean():,.0f} → 막힌 날로 상한 {g2.mean():,.0f} (중앙값 {g.median():,.0f} → {g2.median():,.0f})')

# ───────────── 7. 가격 이상치·통화 점검 ─────────────
print('\n[7] 가격 이상치: 상위 1%를 잘랐을 때 평균 거래액 변화 (활성 단기, 리뷰율 50%, 3박)')
x = a[a['seg'] == '단기(1~3)']; n, g, _ = estimate(x, 0.5, 3)
p99 = x[COL['price']].quantile(0.99)
print(f'  1박가 분위수: {x[COL["price"]].quantile([.5, .9, .99, .999]).round(0).to_dict()}')
print(f'  거래액 평균: 전체 {g.mean():,.0f} → 가격 상위 1% 제외 {g[x[COL["price"]] <= p99].mean():,.0f}')
if COL['region'] in d.columns:
    print('\n  지역별 1박가 중앙값 (다른 지역보다 10배 안팎 크면 현지 통화가 섞인 것)')
    r = a.groupby(COL['region'])[COL['price']].agg(['size', 'median', 'mean']).sort_values('median', ascending=False)
    print(pd.concat([r.head(10), r.tail(5)]))

# ───────────── 8. 견적 정보로 가격 검증 ─────────────
need = ['price_quote_checkin_date', 'price_quote_checkout_date', 'price_quote_total_price']
if all(c in d.columns for c in need):
    print('\n[8] 견적 검증: price 가 실제 1박가인지, 견적이 몇 박 기준인지')
    q = d.copy()
    q['q_nights'] = (pd.to_datetime(q[need[1]], errors='coerce') - pd.to_datetime(q[need[0]], errors='coerce')).dt.days
    q['q_total'] = to_num(q[need[2]])
    q = q[(q['q_nights'] > 0) & (q['q_total'] > 0)]
    q['q_per_night'] = q['q_total'] / q['q_nights']
    q['ratio'] = q['q_per_night'] / q[COL['price']]      # 1 근처 = price 가 1박가, 견적박수 근처 = price 가 총액
    q['ratio_total'] = q['q_total'] / q[COL['price']]
    print(q.groupby('seg', observed=True).agg(숙소수=('ratio', 'size'), 견적박수_중앙값=('q_nights', 'median'),
          견적박수_평균=('q_nights', 'mean'), 최소숙박일_중앙값=(COL['min_nights'], 'median'),
          총액per박_나누기_price=('ratio', 'median'), 총액_나누기_price=('ratio_total', 'median')))
    print('  총액per박÷price 가 1.1~1.4면 price 는 1박가이고 차이는 청소비·수수료. 총액÷price 가 1 근처면 price 가 체류 총액이라 거래액이 과대 계산됨')
    print(f'  견적 박수 = 최소 숙박일인 비율: {(q["q_nights"] == q[COL["min_nights"]]).mean():.1%}')
    print('\n  청소비 등 포함 시 실제 1박당 결제액 (수수료가 총액에 붙는다면 이 값이 거래액 기준)')
    print(q[q['is_active'] == 1].groupby('seg', observed=True)[[COL['price'], 'q_per_night']].agg(['mean', 'median']))

# ───────────── 9. 리뷰 수 지표 간 일관성 ─────────────
if 'number_of_reviews_ly' in d.columns:
    print('\n[9] 최근 12개월 리뷰(ltm)와 지난 1년 리뷰(ly) 비교: 어느 쪽을 쓰느냐에 따라 활성 판정이 달라지는지')
    ly = pd.to_numeric(d['number_of_reviews_ly'], errors='coerce').fillna(0)
    print(pd.crosstab(d['rev'] > 0, ly > 0, rownames=['ltm>0'], colnames=['ly>0'], margins=True))

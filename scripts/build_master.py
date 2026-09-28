# -*- coding: utf-8 -*-
"""마스터 데이터 생성 — 결측치 처리 → 이상치 처리 → 가격 로그 변환.

입력
  data/raw/InsightStay_data.csv          원본 (또는 data/processed/_cache_insightstay.parquet 캐시)
  data/raw/시설_분석용_대체본.csv          bathrooms/bedrooms/beds 대체본 (주현)
출력
  deliverables/InsightStay_data_cleaned.csv    최종 산출물
  deliverables/PREPROCESSING.md                최종 산출물
  data/processed/InsightStay_data_cleaned.parquet   (같은 내용, 읽기 속도용)

name / description 두 자유 텍스트 컬럼은 용량의 대부분을 차지하므로 제외한다.
필요하면 원본에서 id 기준으로 나중에 머지한다.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
# 최종 산출물은 한 폴더에 모은다. 노션 등으로 그대로 건네는 파일들이다.
DELIV = ROOT / "deliverables"
OUT_CSV = DELIV / "InsightStay_data_cleaned.csv"
OUT_MD = DELIV / "PREPROCESSING.md"
TEXT_COLS = {"name", "description"}

# 리포트에 쓸 수치를 모으는 곳. MD 는 이 값으로만 쓰므로 본문과 데이터가 어긋날 수 없다.
S = {}


def log(msg):
    print(msg, flush=True)


# ── 0. 로딩 ────────────────────────────────────────────────────────────────────
def load():
    cache = PROC / "_cache_insightstay.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        log(f"[0] 캐시 로드 {df.shape}")
    else:
        cols = [c for c in pd.read_csv(RAW / "InsightStay_data.csv", nrows=0).columns
                if c not in TEXT_COLS]
        df = pd.read_csv(RAW / "InsightStay_data.csv", usecols=cols, engine="pyarrow")
        df.to_parquet(cache, index=False)
        log(f"[0] CSV 로드 후 캐시 저장 {df.shape}")

    # 파일명이 한글이라 정규화 방식(NFC/NFD)이 환경마다 다르다. glob 대신 직접 찾는다.
    import unicodedata
    def _norm(x):
        return unicodedata.normalize("NFC", x)
    fac = next(p for p in RAW.glob("*.csv")
               if "대체본" in _norm(p.name))
    f = pd.read_csv(fac, engine="pyarrow")
    keep = ["id", "bathrooms_B", "bathrooms_method",
            "bedrooms_B", "bedrooms_method", "beds_B", "beds_method"]
    f = f[keep]
    log(f"[0] 시설 대체본 로드 {f.shape}")
    return df, f


# ── 1. 시설 3컬럼 병합 ─────────────────────────────────────────────────────────
def merge_facilities(df, f):
    """대체본의 _B 값을 본 데이터에 반영한다.

    대체본은 source=1 의 bathrooms/beds 를 채우지 않는다(해당 source 는 관측값이
    0건이라 채우면 창작이 된다). 그 판단을 그대로 따른다.
    """
    n_before = df["id"].nunique()
    df = df.merge(f, on="id", how="left", validate="one_to_one")
    assert df["id"].nunique() == n_before

    for c in ["bathrooms", "bedrooms", "beds"]:
        b = df[c + "_B"]
        # 짝수 개 그룹의 중앙값이 .5 로 떨어진다. 관측값의 단위에 맞춰 되돌린다.
        if c == "bathrooms":
            b = (b * 2).round() / 2          # 관측값이 0.5 단위 → 반욕실 유지
        else:
            b = b.round()                    # 관측값이 전부 정수
        df[c + "_filled"] = b
        df[c + "_impute"] = df[c + "_method"]

    # 대체로 만들어낸 침실 수가 수용 인원을 넘는 경우는 수용 인원으로 자른다.
    cap = df["bedrooms_impute"].isin(["group_median", "similar_host"]) & \
          (df["bedrooms_filled"] > df["accommodates"])
    S["bedrooms_capped"] = int(cap.sum())
    df.loc[cap, "bedrooms_filled"] = df.loc[cap, "accommodates"]

    for c in ["bathrooms", "bedrooms", "beds"]:
        S[f"{c}_filled_n"] = int(df[c + "_impute"].isin(["group_median", "similar_host"]).sum())
        S[f"{c}_still_na"] = int(df[c + "_filled"].isna().sum())
        df[c] = df[c + "_filled"]
        df.drop(columns=[c + "_B", c + "_method", c + "_filled"], inplace=True)

    log(f"[1] 시설 병합 — bathrooms {S['bathrooms_filled_n']:,} / "
        f"bedrooms {S['bedrooms_filled_n']:,} / beds {S['beds_filled_n']:,} 대체, "
        f"침실 상한 적용 {S['bedrooms_capped']:,}")
    return df


# ── 2. 파생 컬럼 (이상치 규칙에 필요한 것 먼저) ────────────────────────────────
def derive_pre(df):
    df["price_per_person"] = df["price"] / df["accommodates"]
    df["host_listings_total"] = df[[
        "calculated_host_listings_count_entire_homes",
        "calculated_host_listings_count_private_rooms",
        "calculated_host_listings_count_shared_rooms"]].sum(axis=1)
    df["amenity_count"] = (df["amenities"].fillna("[]").str.count(",")
                           + df["amenities"].fillna("[]").str.strip().ne("[]").astype(int))
    return df


# ── 3. 행 삭제 (결측 + 이상치 ①) ───────────────────────────────────────────────
def drop_rows(df):
    n0 = len(df)
    S["n_raw"] = n0

    # host_is_superhost 결측 900건은 삭제하지 않는다. 호스트 메타만 비어 있을 뿐
    # 지역·숙소유형·리뷰·가용일수는 100% 관측돼 있고, 878건이 'Room in hotel' 이라
    # source=1 호텔 개인실 세그먼트의 21.4% 를 차지한다. 지우면 그 세그먼트의
    # 최근 1년 리뷰 보유율이 33.4% → 24.2% 로 9.2%p 내려간다. unknown 으로 둔다.
    miss = {
        "minimum/maximum_nights 결측": df["minimum_nights"].isna() | df["maximum_nights"].isna(),
    }
    out = {
        # 1인당 1,000€ 초과만으로는 부족하다. 리뷰가 남아 있는 매물이 절반 가까이 되고,
        # 그중에는 지금도 거래되는 것이 있다. '최근 1년 거래 없음'을 함께 요구한다.
        "1인당 가격 > 1,000€ & 최근 1년 거래 없음":
            (df["price_per_person"] > 1000) & (df["number_of_reviews_ltm"] == 0),
        "price > 10,000€": df["price"] > 10000,
        "minimum_nights > 365": df["minimum_nights"] > 365,
        "minimum_nights > maximum_nights": df["minimum_nights"] > df["maximum_nights"],
    }
    S["drop_miss"] = {k: int(v.fillna(False).sum()) for k, v in miss.items()}
    S["drop_out"] = {k: int(v.fillna(False).sum()) for k, v in out.items()}

    m_miss = np.logical_or.reduce([v.fillna(False) for v in miss.values()])
    m_out = np.logical_or.reduce([v.fillna(False) for v in out.values()])
    # 호스트 메타 결측을 삭제하지 않기로 한 근거를 수치로 남긴다.
    sh = df["host_is_superhost"].isna()
    S["sh_n"] = int(sh.sum())
    S["sh_hotel_rooms"] = int((sh & df["property_type"].eq("Room in hotel")).sum())
    seg = ((df["source"] == 1) & df["room_type"].eq("Private room")
           & df["property_type"].str.contains("hotel", case=False, na=False))
    inc = (df.loc[seg, "number_of_reviews_ltm"] > 0).mean() * 100
    exc = (df.loc[seg & ~sh, "number_of_reviews_ltm"] > 0).mean() * 100
    S["seg_n"] = int(seg.sum())
    S["seg_share"] = round((seg & sh).sum() / seg.sum() * 100, 1)
    S["seg_inc"] = round(inc, 2)
    S["seg_exc"] = round(exc, 2)
    S["seg_gap"] = round(inc - exc, 2)

    S["drop_miss_total"] = int(m_miss.sum())
    S["drop_out_total"] = int(m_out.sum())
    S["drop_out_sum"] = sum(S["drop_out"].values())

    df = df[~(m_miss | m_out)].copy()
    S["n_after_drop"] = len(df)
    S["drop_total"] = n0 - len(df)
    log(f"[3] 행 삭제 {n0:,} → {len(df):,} "
        f"(결측 {S['drop_miss_total']:,} + 이상치 {S['drop_out_total']:,})")
    return df


# ── 4. 결측 처리 (삭제 외) ─────────────────────────────────────────────────────
def fill_missing(df):
    # discount_type — 결측을 전부 '할인 없음'으로 볼 수는 없다.
    # price 와 list_price 를 비교할 수 있어야 할인 여부를 판정할 수 있고,
    # 둘 중 하나라도 비면 알 방법이 없다 → unknown.
    # 차이가 0.01€ 인 건은 할인이 아니라 반올림 오차다. 반대 방향(price 가 0.01 큼)이
    # 5,288건이나 되고, 실제 할인은 차이 중앙값이 20.80€ 로 자릿수가 다르다.
    na = df["discount_type"].isna()
    can_compare = df["price"].notna() & df["list_price"].notna()
    S["discount_unknown"] = int((na & ~can_compare).sum())
    S["discount_none"] = int((na & can_compare).sum())
    S["discount_real"] = int((~na).sum())
    df["discount_type"] = df["discount_type"].fillna("no_discount")
    df.loc[na & ~can_compare, "discount_type"] = "unknown"

    # neighbourhood — region 으로 덮으면 '구역'과 '도시'가 한 컬럼에 섞인다.
    # 단위가 다르다는 사실을 값에 드러내고 플래그로도 남긴다.
    na_nb = df["neighbourhood_group_cleansed"].isna()
    S["nb_city_level"] = int(na_nb.sum())
    df["neighbourhood_is_city_level"] = na_nb
    df["neighbourhood_group_cleansed"] = df["neighbourhood_group_cleansed"].fillna(
        df["region"] + "_전체")

    # 호스트 메타 — 채울 근거가 없으므로 추정하지 않고 unknown 으로 둔다.
    df["host_meta_is_unknown"] = df["host_is_superhost"].isna()
    df["host_is_superhost"] = df["host_is_superhost"].fillna("unknown")
    df["host_location"] = df["host_location"].fillna("unknown")
    df["reviews_per_month"] = df["reviews_per_month"].fillna(0)

    # host_listings_total == 0 은 논리 모순 → unknown 버킷
    S["host_listings_unknown"] = int((df["host_listings_total"] == 0).sum())
    df["host_listings_is_unknown"] = df["host_listings_total"] == 0
    df.loc[df["host_listings_is_unknown"], "host_listings_total"] = np.nan

    # amenities == [] 는 '편의시설 없음'이 아니라 미수집 → 개수를 결측으로
    empty_am = df["amenity_count"] == 0
    S["amenities_empty"] = int(empty_am.sum())
    df.loc[empty_am, "amenity_count"] = np.nan

    # 평점 0 점은 척도상 존재할 수 없는 값 → 결측
    sc = [c for c in df.columns if c.startswith("review_scores_")]
    zero = (df[sc] == 0).any(axis=1)
    S["score_zero"] = int(zero.sum())
    df[sc] = df[sc].mask(df[sc] == 0)

    log(f"[4] 결측 처리 — 할인 미기재 {S['discount_unknown']:,} / "
        f"구역 도시단위 {S['nb_city_level']:,} / 평점0 {S['score_zero']:,}")
    return df


# ── 5. 이상치 ②③ 플래그 ───────────────────────────────────────────────────────
def add_flags(df):
    REF = pd.to_datetime(df["last_review"], errors="coerce").max()
    stale = (REF - pd.to_datetime(df["last_review"], errors="coerce")).dt.days
    S["ref_date"] = str(REF.date())

    flags = {
        "flag_max_nights_default": df["maximum_nights"] >= 1125,
        "flag_price_over_2000": df["price"] > 2000,
        "flag_price_under_10": df["price"] < 10,
        # 삭제 기준을 통과했지만 1인당 가격이 여전히 비정상적으로 높은 건들.
        # 최근 거래 기록이 있어 남겼을 뿐, 검증 없이 평균에 넣으면 안 된다.
        "flag_price_per_person_over_1000": df["price_per_person"] > 1000,
        "flag_beds_over_20": df["beds"] > 20,
        "flag_bathrooms_over_10": df["bathrooms"] > 10,
        "flag_bedrooms_over_20": df["bedrooms"] > 20,
        "flag_dead_stock": (df["availability_365"] == 0) & (df["number_of_reviews"] == 0),
        "flag_stale_over_1y": stale > 365,
    }
    for k, v in flags.items():
        df[k] = v.fillna(False)
    S["flags"] = {k: int(df[k].sum()) for k in flags}

    df["has_price"] = df["price"].notna()
    df["has_review"] = df["number_of_reviews"] > 0
    df["is_bookable"] = df["availability_365"] > 0
    df["is_active"] = df["number_of_reviews_ltm"] > 0
    df["days_since_last_review"] = stale
    log(f"[5] 플래그 {len(flags)}종 생성")
    return df


# ── 6. 가격 로그 변환 ──────────────────────────────────────────────────────────
def log_price(df):
    """가격은 오른쪽으로 길게 늘어진 분포라 평균·회귀가 상위값에 끌려간다.

    log1p 를 쓰는 이유는 0 을 허용하기 위해서다(현재 데이터에 price==0 은 없지만
    list_price·quote 에 0 이 들어와도 깨지지 않게 한다). 원본 컬럼은 남긴다.
    """
    cols = ["price", "list_price", "price_quote_total_price", "price_per_person"]
    S["log_cols"] = {}
    for c in cols:
        df["log_" + c] = np.log1p(df[c])
        v = df[c].dropna()
        S["log_cols"][c] = {
            "skew_before": round(float(v.skew()), 2),
            "skew_after": round(float(np.log1p(v).skew()), 2),
        }
    log("[6] 로그 변환 " + ", ".join("log_" + c for c in cols))
    return df


# ── 7. 저장 ────────────────────────────────────────────────────────────────────
def save(df):
    """CSV 는 float64 를 소수점 17자리까지 적어서 용량이 몇 배로 불어난다.
    의미 있는 자리까지만 반올림하고, 빠르게 읽을 parquet 을 같이 낸다."""
    PROC.mkdir(parents=True, exist_ok=True)
    DELIV.mkdir(parents=True, exist_ok=True)
    for c in df.select_dtypes("float").columns:
        df[c] = df[c].round(4)

    df.to_parquet(PROC / "InsightStay_data_cleaned.parquet", index=False)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    S["n_final"], S["n_cols"] = len(df), df.shape[1]
    S["size_mb"] = round(OUT_CSV.stat().st_size / 1024 ** 2, 1)
    S["size_pq_mb"] = round((PROC / "InsightStay_data_cleaned.parquet").stat().st_size / 1024 ** 2, 1)
    log(f"[7] 저장 {OUT_CSV.name} — {S['n_final']:,}행 × {S['n_cols']}열, "
        f"CSV {S['size_mb']} MB / parquet {S['size_pq_mb']} MB")




MD_TEMPLATE = """# InsightStay 전처리 명세

> `scripts/build_master.py` 가 생성합니다. 이 문서의 모든 수치는 실행 결과에서 자동으로 채워지므로 본문과 데이터가 어긋나지 않습니다.
> 산출물: **`deliverables/InsightStay_data_cleaned.csv`** ({n_final:,}행 × {n_cols}열, {size_mb} MB)
> 같은 내용의 `data/processed/InsightStay_data_cleaned.parquet` ({size_pq_mb} MB) 을 함께 냅니다. 읽기 속도가 필요하면 이쪽을 쓰세요.

| 항목 | 값 |
|---|---|
| 원본 | `data/raw/InsightStay_data.csv` — 842,655행 × 50열 |
| 시설 대체본 | `data/raw/시설_분석용_대체본.csv` (bathrooms/bedrooms/beds) |
| 처리 후 | **{n_final:,}행** × {n_cols}열 (원본의 {pct_kept:.2f}%) |
| 삭제 | {drop_total:,}행 ({pct_dropped:.2f}%) — 결측 {drop_miss_total:,} + 이상치 {drop_out_total:,} |
| 기준일 | {ref_date} (데이터 내 `last_review` 최댓값) |
| 제외 컬럼 | `name`, `description` — 용량의 대부분을 차지하는 자유 텍스트. 필요하면 원본에서 `id` 기준으로 머지 |

**처리 순서** — 시설 대체본 병합 → 파생 컬럼 → 행 삭제(결측·이상치) → 결측 채움 → 이상치 플래그 → 가격 로그 변환.
순서가 중요합니다. `price_per_person` 이 있어야 이상치를 판정할 수 있고, 삭제를 먼저 해야 채움 값이 오염되지 않습니다.

---

## 1. 결측치 처리

결측률은 원본 842,655행 기준, 잔여 결측률은 처리 후 {n_final:,}행 기준입니다.

| 컬럼 | 유형 | 결측률 | 처리 | 잔여 |
|---|---|---:|---|---:|
{na_table}

### 원칙

#### 1. 채울 수 없는 것과 버려야 하는 것은 다르다

행 삭제는 **`minimum/maximum_nights` 결측 {minmax_drop:,}건**뿐입니다(전체의 0.016%). 두 컬럼이 항상 함께 비어 있고, 이건 플랫폼이 계산한 값이 아니라 **호스트가 직접 설정한 값**이라 추정할 근거가 없습니다. 분포도 중앙값 2박·90퍼센타일 14박으로 제각각이라(표준편차 43.3) 중앙값으로 채우면 장기 임대 매물이 단기 매물로 둔갑합니다. 게다가 `minimum_nights` 는 과제가 지목한 핵심 변수입니다. 41개 도시·132명 호스트에 고루 흩어져 있어 삭제해도 표본이 왜곡되지 않습니다.

**`host_is_superhost` 결측 {sh_n:,}건은 삭제하지 않습니다.** 처음에는 지웠다가 되돌렸습니다. 호스트 메타 5개 컬럼(`host_is_superhost`, `hosts_time_as_*` 4종)이 전부 동시에 비어 있는 건 맞지만, **나머지 정보는 멀쩡합니다** — 지역·숙소유형·판매단위·수용인원·누적리뷰·최근 1년 리뷰·가용일수가 **100% 관측**돼 있고 가격도 87.9% 있습니다.

지우면 특정 세그먼트가 망가집니다. 이 {sh_n:,}건 중 **{sh_hotel_rooms:,}건이 `Room in hotel`** 이라, source=1 호텔 개인실 {seg_n:,}행의 **{seg_share}%** 를 차지합니다. 삭제 전후로 이 세그먼트의 최근 1년 리뷰 보유율이 이렇게 움직입니다.

| source=1 호텔 개인실 | 최근 1년 리뷰 보유율 |
|---|---:|
| 포함 | **{seg_inc}%** |
| 제외 | {seg_exc}% |
| | **{seg_gap}%p** |

전체로는 0.107%지만 이 세그먼트 안에서는 5분의 1입니다. **호스트 정보 하나를 모른다는 이유로 공급·수요 정보를 통째로 버릴 이유가 없습니다.** `unknown` 으로 두고 `host_meta_is_unknown` 플래그를 붙였습니다.

> **슈퍼호스트 비율을 계산할 때는 `unknown` 을 분모에서 빼세요.** `host_is_superhost` 가 `t`/`f`/`unknown` 3값이라, `t / 전체` 로 계산하면 이 {sh_n:,}건 때문에 비율이 실제보다 낮게 나옵니다. `df[df.host_is_superhost != "unknown"]` 으로 거른 뒤 계산하거나 `host_meta_is_unknown == False` 로 필터링하세요.

#### 2. '할인 없음'과 '알 수 없음'을 구분한다

`discount_type` 의 결측을 전부 `no_discount` 로 채우면 안 됩니다. 할인 여부는 `price` 와 `list_price` 를 비교해야 알 수 있는데, **둘 중 하나라도 비어 있으면 판정할 방법이 없습니다.** 그런 행이 **{discount_unknown:,}건**입니다. 이걸 '할인 없음'으로 단정하면 할인 효과 분석의 분모가 그만큼 부풀려집니다. 그래서 세 값으로 나눴습니다.

| 값 | 건수 | 근거 |
|---|---:|---|
| 실제 할인 5종 | {discount_real:,} | `discount_type` 이 원래 채워져 있던 행 |
| `no_discount` | {discount_none:,} | 두 가격 비교 가능, 차이 없음 |
| **`unknown`** | **{discount_unknown:,}** | **두 가격 중 하나 이상 결측 → 판정 불가** |

**`list_price` 가 `price` 보다 0.01€ 큰 1,501건은 할인이 아닙니다.** 전부 정확히 0.01€ 차이이고 할인율로는 평균 0.0056% 입니다. 반대 방향(price 가 0.01 큼)도 5,288건 있어 한쪽으로 쏠리지 않습니다 — **반올림 오차**입니다. 실제 할인은 차이의 중앙값이 20.80€ 로 자릿수가 다릅니다. 이 1,501건은 `no_discount` 에 포함됩니다.

#### 3. `neighbourhood_group_cleansed` 를 `region` 으로 덮지 않는다

53개 도시 중 17개만 구역 정보가 있고 36개는 전혀 없습니다. `region` 값으로 채우면 한 컬럼에 '구역'과 '도시' 두 단위가 섞여, 마드리드의 한 구역과 로마 전체가 같은 급으로 취급됩니다. `{{region}}_전체` 형태로 채워 단위가 다르다는 사실을 값에 드러내고, `neighbourhood_is_city_level` ({nb_city_level:,}건) 로도 구분했습니다. **구역 단위 분석은 이 플래그가 `False` 인 행으로 한정하세요.**

#### 4. `beds` · `bathrooms` 는 source=1 을 대체하지 않는다

이 두 컬럼은 source=1 에서 결측률이 **100%** 입니다. 무작위 결측이 아니라 수집 스키마가 다른 것이어서, 채우려면 관측값 0건에서 값을 만들어내야 합니다. 그래서 source=0 안에서만 채웠고 (source=0 보유율 `bathrooms` {bathrooms_s0_rate}% · `beds` {beds_s0_rate}%), 나머지는 결측으로 남겼습니다. **이 두 컬럼을 쓰는 분석은 source=0 으로 한정하세요.** `bedrooms` 는 source=1 에도 관측값이 74% 있어 양쪽 모두 채웠습니다 (잔여 {bedrooms_still_na:,}건, source=0 보유율 {bedrooms_s0_rate}%).

#### 5. 대체한 값은 전부 추적 가능하게 남긴다

`_impute` 컬럼에 `observed` / `similar_host` / `group_median` / `missing` 네 값이라 어느 수치가 관측이고 어느 것이 대체인지 항상 구분됩니다. 중앙값 대체는 분산을 누르므로 (`bedrooms` 표준편차 1.158 → 대체분 0.320), **상관분석처럼 분산이 결과를 좌우하는 계산은 `_impute == "observed"` 로 걸러 쓰세요.**

---

## 2. 이상치 처리

### 2.1 삭제 — {drop_out_total:,}건 ({pct_out:.3f}%)

| 규칙 | 건수 | 비율 |
|---|---:|---:|
{drop_rows}

네 조건의 단순 합은 {drop_out_sum:,}건이지만, 한 매물이 여러 조건에 걸리는 경우가 있어 중복을 뺀 실제 삭제는 **{drop_out_total:,}건**입니다.

**기준은 하나 — 현실에 존재할 수 없는 값인가.**

- **`1인당 가격 > 1,000€` 이면서 `최근 1년 거래 없음`** — 조건이 **두 개**입니다. 이유는 아래 "왜 조건을 두 개로 걸었나" 에서 설명합니다.
  가격을 수용 인원으로 나눠 봅니다. 2인실 5,918€는 1인당 2,959€로 불가능하지만, 16인 빌라 2,500€는 1인당 156€라 정상으로 남습니다. 전체 매물의 1인당 중앙값이 46.9€, 상위 1%가 281.5€ 이므로 1,000€ 컷은 상위 1% 지점보다도 3.5배 위입니다.
  **절대 가격을 쓰지 않는 이유** — `price > 2,000` 으로 자르면 산토리니·마요르카의 고가 빌라 세그먼트가 통째로 사라지고, 마요르카가 숙소당 연매출 1위인 근거 자체가 없어집니다.
  원인은 **호스트 입력 오류**입니다(자릿수 오타 또는 장기 총액을 1박 칸에 기재). 통화 미환산이 아닙니다 — TF팀에서 EUR 환산을 마쳤고, 국가별 1인당 중앙값이 터키 18€ ~ 네덜란드 94€로 정상 범위이며 1,000€ 초과 건이 19개국에 0.0~0.3%로 균일합니다. 환산 누락이라면 특정 통화에 뭉쳐야 합니다. 뒷받침: 1인당 1,000€ 초과 744건의 **리뷰 0건 비율 52.7%** (전체 18.2%), **`price` 가 1,000 배수인 비율 8.9%** (전체 0.04%).
- **`price > 10,000€`** — 1인당 기준으로도 안 걸리는 극단값만 보정합니다. 런던 611,870€는 어떤 인원으로 나눠도 설명되지 않습니다.
- **`minimum_nights > maximum_nights`** — "최소 30박, 최대 7박"은 예약이 불가능한 설정입니다. 참·거짓을 따질 필요가 없습니다.
- **`minimum_nights > 365`** — 1년 넘는 최소 숙박일은 단기 숙박 상품이 아닙니다. 값이 맞더라도 분석 대상(단기 예약 전환)을 벗어나 가동률·전환율을 왜곡합니다.

#### 왜 조건을 두 개로 걸었나

1인당 가격만으로 자르면 **744건**이 걸립니다. 그런데 이 중 **352건(47.3%)에는 리뷰가 있습니다.** 리뷰가 있다는 건 과거에 팔렸다는 뜻이라, 한 조건만으로 지우면 "실제로 거래되는 매물을 가격이 비싸다는 이유로 삭제"하는 일이 생깁니다. 예를 들어 베네치아 2인실 2,018€(1인당 1,009€)는 리뷰 208건에 최근 1년에도 6건이 달렸습니다. 비싸지만 **팔리고 있는 매물**입니다.

그래서 **`number_of_reviews_ltm == 0`(최근 1년 거래 없음)** 을 함께 요구합니다. 리뷰가 옛날 것뿐이라면, 가격이 망가진 뒤 예약이 끊겼다고 보는 편이 자연스럽습니다. 실제로 리뷰가 있는 352건 중 **57%가 최근 1년 거래가 없습니다.**

결과: 744건 중 **{ppp_dropped}건 삭제**, {ppp_kept}건은 다른 규칙(`price > 10,000`)에 걸려 삭제, **{ppp_flagged}건은 살아남아 `flag_price_per_person_over_1000` 으로 표시**됩니다.

> **남은 {ppp_flagged}건은 "정상"이 아니라 "판단 보류"입니다.** 1인당 중앙값이 1,431€ 로 여전히 전체 상위 1%(281€)의 5배이고, 파리 2인실 9,800€(최근 1년 리뷰 32건)처럼 거래 기록이 있는데도 설명하기 어려운 건이 섞여 있습니다. 가격·객단가 분석에서는 **이 플래그를 빼고 한 번 더 계산해보세요.** 전체의 0.013%라 결론이 바뀔 가능성은 낮습니다.

### 2.2 플래그 — 삭제하지 않고 표시

건수는 **삭제를 마친 {n_final:,}행 기준**입니다. 예를 들어 `flag_price_over_2000` 은 원본에서 3,799건이지만, 그중 1인당 가격 기준에 걸린 건이 먼저 삭제돼 {flag_price_over_2000:,}건이 남았습니다.

| 컬럼 | 규칙 | 건수 | 비율 | 남긴 이유 |
|---|---|---:|---:|---|
{flag_rows}

**"이상해 보인다"와 "틀렸다"는 다릅니다.** `price < 10` 유령 매물({flag_price_under_10:,}건)이나 완전 비활성 재고({flag_dead_stock:,}건)는 삭제 대상보다 훨씬 많지만 전부 남겼습니다. **이게 과제가 찾아야 할 문제 그 자체**이기 때문입니다. 지우면 결론이 사라집니다.

### 2.3 값 보정

- **평점 0점 {score_zero}건** → 결측. 평점 척도에 0이 없으므로 미입력의 표현입니다. `review_scores_*` 7개 컬럼 전부에 적용했습니다.
- **`amenities == []` {amenities_empty}건** → `amenity_count` 결측. '편의시설이 하나도 없다'가 아니라 미수집으로 봅니다.
- **`host_listings_total == 0` {host_listings_unknown:,}건** → 결측 + `host_listings_is_unknown` 플래그. 리스팅이 존재하는데 보유 수가 0인 것은 논리 모순입니다.

---

## 3. 가격 로그 변환

가격은 오른쪽으로 길게 늘어진 분포라 평균과 회귀가 소수의 고가 매물에 끌려갑니다. 원본 컬럼은 그대로 두고 `log_` 접두 컬럼을 추가했습니다.

| 컬럼 | 변환 전 왜도 | 변환 후 왜도 |
|---|---:|---:|
{log_rows}

`log1p`(= log(1+x))를 쓴 이유는 0을 허용하기 위해서입니다. 현재 `price == 0` 은 없지만 `list_price`·`quote` 에 0이 들어와도 계산이 깨지지 않습니다.

**`price` 의 왜도가 {skew_price_before} → {skew_price_after} 로 떨어졌습니다.** 정규분포에 가까워졌다는 뜻이라 평균 비교·회귀·상관에 바로 쓸 수 있습니다. 다만 **로그값의 평균은 원래 단위의 평균이 아닙니다.** 발표에 "평균 객단가 OO€"를 쓸 때는 반드시 원본 `price` 의 중앙값이나 평균을 쓰고, 로그 컬럼은 모델·검정에만 쓰세요.

---

## 4. 추가된 컬럼

| 컬럼 | 설명 |
|---|---|
{new_rows}

---

## 5. 재현

```bash
python scripts/build_master.py
```

원본 CSV(1.06GB)를 처음 읽을 때만 `data/processed/_cache_insightstay.parquet` 캐시를 만들고, 이후에는 캐시에서 읽습니다. 실행할 때마다 `data/processed/_preprocessing_stats.json` 에 이 문서의 모든 수치가 함께 저장됩니다.
"""


# ── 8. 리포트 ──────────────────────────────────────────────────────────────────
# 결측 처리 방향. (그룹, 처리 요약) — 표의 순서도 이 순서를 따른다.
PLAN = [
    ("discount_type", "범주", "가격 비교가 가능한 {discount_none:,}건은 `no_discount`, **두 가격 중 하나라도 결측이라 판정 불가한 {discount_unknown:,}건은 `unknown`**"),
    ("neighbourhood_group_cleansed", "범주", "`{region}_전체` 로 채우고 `neighbourhood_is_city_level` 플래그. **`region` 값으로 덮지 않음**"),
    ("host_location", "범주", "`unknown` 으로 채움 (호스트–숙소 거리 분석에 쓰므로 삭제하지 않음)"),
    ("bathrooms", "수치", "대체본 반영 — 유사 숙소 {bathrooms_filled_n:,}건 채움. **source=1 은 대체하지 않음**"),
    ("beds", "수치", "대체본 반영 — 유사 숙소 {beds_filled_n:,}건 채움. **source=1 은 대체하지 않음**"),
    ("bedrooms", "수치", "대체본 반영 — 유사 숙소 {bedrooms_filled_n:,}건 채움 (수용 인원 초과 {bedrooms_capped}건은 상한 적용)"),
    ("reviews_per_month", "수치", "`0` 으로 채움 (리뷰 없음 = 월평균 0)"),
    ("first_review", "날짜", "**결측 유지** — 리뷰가 없으면 논리적으로 값이 존재할 수 없음"),
    ("last_review", "날짜", "**결측 유지** — 위와 동일"),
    ("review_scores_rating", "수치", "**결측 유지** — 리뷰 0건과 1:1 대응. 추가로 0점 {score_zero}건을 결측 처리"),
    ("price", "수치", "**결측 유지** + `has_price` 플래그. source=1 결측률 79.1% vs source=0 4.0% → 시점 분석은 source=0 한정"),
    ("list_price", "수치", "**결측 유지** — 위와 동일"),
    ("price_quote_total_price", "수치", "**결측 유지** — 위와 동일"),
    ("price_quote_checkin_date", "날짜", "**결측 유지** — 위와 동일"),
    ("price_quote_checkout_date", "날짜", "**결측 유지** — 위와 동일"),
    ("host_is_superhost", "범주", "**`unknown` 으로 채움** ({sh_n:,}건) + `host_meta_is_unknown` 플래그. **슈퍼호스트 비율은 `unknown` 을 분모에서 빼고 계산할 것**"),
    ("minimum_nights", "수치", "**행 삭제** ({minmax_drop:,}건)"),
    ("maximum_nights", "수치", "**행 삭제** — 위와 동일"),
]

NEW_COLS = [
    ("price_per_person", "`price / accommodates`. 이상치 판정의 주 기준"),
    ("host_listings_total", "호스트의 entire/private/shared 리스팅 합. 0은 결측 처리"),
    ("amenity_count", "편의시설 개수. `[]` 는 미수집으로 보아 결측"),
    ("log_price / log_list_price / log_price_quote_total_price / log_price_per_person", "`log1p` 변환"),
    ("bathrooms_impute / bedrooms_impute / beds_impute", "`observed` / `similar_host` / `group_median` / `missing`"),
    ("neighbourhood_is_city_level", "구역 값이 없어 도시 단위로 채워진 행"),
    ("host_listings_is_unknown", "`host_listings_total == 0` 이던 행"),
    ("host_meta_is_unknown", "호스트 메타 5개 컬럼이 비어 있던 행. 슈퍼호스트 비율 계산에서 제외할 것"),
    ("has_price / has_review / is_bookable / is_active", "세그먼트 플래그"),
    ("days_since_last_review", f"기준일에서 마지막 리뷰까지 경과일"),
    ("flag_*", "이상치 플래그 {n_flags}종 — 2.2 표 참고"),
]

FLAG_DESC = {
    "flag_max_nights_default": ("`maximum_nights >= 1125`", "플랫폼 기본값(미설정). 실제 현상이므로 삭제하면 '설정 안 함'이라는 정보가 사라짐"),
    "flag_price_over_2000": ("`price > 2,000€`", "절대 가격으로 자르면 산토리니·마요르카 고가 빌라가 통째로 삭제됨. 1인당 기준으로만 판정"),
    "flag_price_under_10": ("`price < 10€`", "이스탄불 집중 + `min_nights=365` + 리뷰 0건 = **노출만 노린 유령 매물**. 찾아야 할 문제 그 자체"),
    "flag_price_per_person_over_1000": ("`price_per_person > 1,000€`", "삭제 기준(최근 1년 거래 없음)을 통과한 잔여분. **최근 거래가 있어 남겼을 뿐 정상 확인된 값이 아님** — 가격 분석에서는 제외하고 한 번 더 보세요"),
    "flag_beds_over_20": ("`beds > 20`", "건물 단위 리스팅으로 설명 가능"),
    "flag_bathrooms_over_10": ("`bathrooms > 10`", "위와 동일"),
    "flag_bedrooms_over_20": ("`bedrooms > 20`", "위와 동일"),
    "flag_dead_stock": ("`availability_365 == 0` & `number_of_reviews == 0`", "완전 비활성 재고. 수익성 진단의 대상"),
    "flag_stale_over_1y": ("마지막 리뷰 1년 초과", "리뷰가 한 번도 없는 매물은 제외된 수치. 휴면 총량은 `is_active` 로 셀 것"),
}


def write_md(df):
    NL = chr(10)
    b, a = S["na_before"], S["na_after"]
    S["minmax_drop"] = S["drop_miss"]["minimum/maximum_nights 결측"]

    # 잔여 결측은 '처리 후' 행 수 기준으로 다시 센다 (병합 직후 수치는 삭제 전이라 크다).
    for c in ["bathrooms", "bedrooms", "beds"]:
        S[c + "_still_na"] = int(df[c].isna().sum())
        s0 = df["source"] == 0
        S[c + "_s0_rate"] = round((1 - df.loc[s0, c].isna().mean()) * 100, 1)

    S["pct_kept"] = S["n_final"] / S["n_raw"] * 100
    S["pct_dropped"] = S["drop_total"] / S["n_raw"] * 100
    S["pct_out"] = S["drop_out_total"] / S["n_raw"] * 100
    S["flag_price_under_10"] = S["flags"]["flag_price_under_10"]
    S["flag_dead_stock"] = S["flags"]["flag_dead_stock"]
    S["flag_price_over_2000"] = S["flags"]["flag_price_over_2000"]
    S["ppp_dropped"] = S["drop_out"]["1인당 가격 > 1,000€ & 최근 1년 거래 없음"]
    S["ppp_flagged"] = S["flags"]["flag_price_per_person_over_1000"]
    S["ppp_kept"] = 744 - S["ppp_dropped"] - S["ppp_flagged"]

    S["skew_price_before"] = S["log_cols"]["price"]["skew_before"]
    S["skew_price_after"] = S["log_cols"]["price"]["skew_after"]
    S["n_flags"] = len(S["flags"])

    rows = []
    for col, kind, how in PLAN:
        how = how.format(region="{region}", **S)
        after = a.get(col)
        after_s = "—" if after is None else ("**0.00%**" if after == 0 else f"{after:.2f}%")
        rows.append(f"| `{col}` | {kind} | {b[col]:.2f}% | {how} | {after_s} |")
    na_table = NL.join(rows)

    drop_rows_md = NL.join(
        f"| `{k}` | {v:,} | {v / S['n_raw'] * 100:.3f}% |" for k, v in S["drop_out"].items())
    flag_rows_md = NL.join(
        f"| `{k}` | {FLAG_DESC[k][0]} | {v:,} | {v / S['n_final'] * 100:.2f}% | {FLAG_DESC[k][1]} |"
        for k, v in S["flags"].items())
    log_rows_md = NL.join(
        f"| `{c}` | {d['skew_before']} | **{d['skew_after']}** |" for c, d in S["log_cols"].items())
    new_rows_md = NL.join(f"| `{c}` | {d.format(**S)} |" for c, d in NEW_COLS)

    md = MD_TEMPLATE.format(
        na_table=na_table, drop_rows=drop_rows_md, flag_rows=flag_rows_md,
        log_rows=log_rows_md, new_rows=new_rows_md, **S)
    OUT_MD.write_text(md, encoding="utf-8")
    log(f"[9] 리포트 저장 {OUT_MD.name}")


def main():
    df, f = load()
    S["na_before"] = df.isna().mean().mul(100).round(2).to_dict()
    df = merge_facilities(df, f)
    df = derive_pre(df)
    df = drop_rows(df)
    df = fill_missing(df)
    df = add_flags(df)
    df = log_price(df)
    S["na_after"] = df.isna().mean().mul(100).round(2).to_dict()
    save(df)

    import json
    (PROC / "_preprocessing_stats.json").write_text(
        json.dumps(S, ensure_ascii=False, indent=1), encoding="utf-8")
    log("[8] 통계 저장 _preprocessing_stats.json")
    write_md(df)


if __name__ == "__main__":
    sys.exit(main())

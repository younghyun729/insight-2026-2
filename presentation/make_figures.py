"""발표용 차트 — presentation/figures/*.png 를 만든다.

마스터 데이터(data/processed/InsightStay_data_cleaned.parquet)에서 모든 값을 다시 계산한다.
색 규칙 (presentation/FORMAT_GUIDE.md 3장):
  파랑 = 기준 · 단기 · 팔림   주황 = 문제 · 중기   청록 = 장기   회색 = 제외 · 참고
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from scipy import stats

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "presentation" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
GRAY, LIGHT = "#b5b3ad", "#e1e0d9"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"

for _f in ["Malgun Gothic", "AppleGothic", "NanumGothic"]:
    if any(_f == f.name for f in mpl.font_manager.fontManager.ttflist):
        mpl.rcParams["font.family"] = _f
        break
mpl.rcParams.update({
    "axes.unicode_minus": False, "figure.dpi": 100, "savefig.dpi": 200,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": LIGHT, "grid.linewidth": 0.8,
    "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlepad": 14,
    "font.size": 11,
})


def save(fig, name, subtitle=None):
    if subtitle:
        fig.text(0.01, -0.05, subtitle, fontsize=9, color=MUTED, ha="left", va="top")
    fig.savefig(OUT / name, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print("saved", name)


def bar_labels(ax, bars, fmt, color=INK, pad=0.6, size=10):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + pad, fmt(h), ha="center", va="bottom", fontsize=size, color=color)


d = pd.read_parquet(ROOT / "data/processed/InsightStay_data_cleaned.parquet")
s = d[d["source"] == 0].copy()
s["stay"] = pd.cut(s["minimum_nights"], [0, 3, 29, np.inf], labels=["단기", "중기", "장기"]).astype(str)
s["norev"] = (s["number_of_reviews_ltm"] == 0).astype(int)
s["mid"] = (s["stay"] == "중기").astype(int)
s["entire"] = (s["room_type"] == "Entire home/apt").astype(int)
s["lpr"] = np.log(s["price_rel"])
s["a5"] = s["amenity_rel"] / 5
u = s[s["stay"] != "장기"].copy()

# ── 01. source 0 vs 1 ──────────────────────────────────────────────
metrics = {
    "가격 결측": lambda g: g["price"].isna().mean(),
    "예약 가능일 0": lambda g: (g["availability_365"] == 0).mean(),
    "최근 1년 리뷰 0": lambda g: (g["number_of_reviews_ltm"] == 0).mean(),
}
vals = {src: [f(d[d.source == src]) * 100 for f in metrics.values()] for src in [0, 1]}
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(len(metrics)); w = 0.36
b0 = ax.bar(x - w / 2 - 0.01, vals[0], w, color=BLUE, label=f"source 0 (분석 대상 · {(d.source == 0).sum():,}건)")
b1 = ax.bar(x + w / 2 + 0.01, vals[1], w, color=GRAY, label=f"source 1 (과거값 이월 · {(d.source == 1).sum():,}건)")
bar_labels(ax, b0, lambda v: f"{v:.1f}%"); bar_labels(ax, b1, lambda v: f"{v:.1f}%")
ax.set_xticks(x, list(metrics)); ax.set_ylim(0, 112); ax.set_yticks([])
ax.legend(frameon=False, loc="upper left", fontsize=10, ncol=2)
ax.set_title("source 1은 가격 · 달력 · 최근 리뷰가 '현재'가 아니다", loc="left")
save(fig, "01_source_compare.png", "source 1의 마지막 리뷰 중앙값 2024-09-27 (source 0은 2026-05-25)")

# ── 02. 도시 규모 vs 숙소당 수익 ────────────────────────────────────
sp = s[s["has_price"]].assign(rev=lambda t: t["price"] * t["occ_review"] * 365)
city = pd.DataFrame({"공급": d.groupby("region").size(), "수익": sp.groupby("region")["rev"].mean()})
fig, ax = plt.subplots(figsize=(8, 4.8))
ax.scatter(city["공급"], city["수익"] / 1000, s=36, color=BLUE, alpha=0.55, edgecolor="white", linewidth=0.8)
hl = {"london": "런던", "paris": "파리", "sicily": "시칠리아", "edinburgh": "에든버러", "barcelona": "바르셀로나", "venice": "베네치아"}
for k, lab in hl.items():
    if k in city.index:
        cx, cy = city.loc[k, "공급"], city.loc[k, "수익"] / 1000
        ax.scatter(cx, cy, s=60, color=ORANGE, edgecolor="white", linewidth=1, zorder=3)
        ax.annotate(lab, (cx, cy), xytext=(6, 4), textcoords="offset points", fontsize=10, color=INK)
ax.set_xscale("log")
ax.set_xlabel("공급 (지역 매물 수, 로그)"); ax.set_ylabel("숙소당 추정 연매출 (천 €)")
ax.grid(axis="both")
ax.set_title("매물이 많은 도시가 돈을 버는 도시는 아니다", loc="left")
save(fig, "02_city_supply_vs_revenue.png", "숙소당 연매출 = 1박 가격 × 리뷰 기반 가동률 × 365 (source 0 · 가격 보유, 성수기 가격 기준 상한)")

# ── 03. 최소 숙박별 무거래율 ────────────────────────────────────────
bins = [0, 1, 2, 3, 4, 5, 7, 14, 29, 30, 31, np.inf]
labs = ["1", "2", "3", "4", "5", "6–7", "8–14", "15–29", "30", "31", "32+"]
r = s.groupby(pd.cut(s["minimum_nights"], bins, labels=labs))["norev"].mean() * 100
cols = [BLUE] * 3 + [ORANGE] * 5 + [AQUA] * 3
fig, ax = plt.subplots(figsize=(9, 4.2))
bars = ax.bar(range(len(r)), r.values, color=cols, width=0.7)
bar_labels(ax, bars, lambda v: f"{v:.0f}%", size=9.5)
ax.set_xticks(range(len(r)), [f"{l}박" for l in labs], fontsize=9.5)
ax.set_yticks([]); ax.set_ylim(0, 100)
for x0, x1, lab, c in [(-0.4, 2.4, "단기 1–3박", BLUE), (2.6, 7.4, "중기 4–29박", ORANGE), (7.6, 10.4, "장기 30박+", AQUA)]:
    ax.plot([x0, x1], [96, 96], color=c, lw=2.5, solid_capstyle="round")
    ax.text((x0 + x1) / 2, 98, lab, ha="center", va="bottom", fontsize=10, color=INK2)
ax.set_title("최소 숙박 4박부터 '1년 동안 한 번도 안 팔린' 매물이 계단처럼 늘어난다", loc="left", pad=26)
save(fig, "03_minnights_norev.png", "무거래율 = 최근 1년 리뷰 0건 비율 (source 0, 678,130건)")

# ── 04. 2×3 칸 ──────────────────────────────────────────────────────
cnt = s["cell"].astype(int).value_counts()
info = {
    1: ("O · 단기", "도시 관광지의 정상 매물", GRAY, "유지"),
    2: ("O · 중기", "휴양지 별장 · 주 단위", ORANGE, "전략 ①"),
    3: ("O · 장기", "규제 도시의 1–2인 장기 체류", AQUA, "전략 ③"),
    4: ("X · 단기", "휴양지 · 비싸고 상품력 낮음", GRAY, "신규 24,602건 → 전략 ②"),
    5: ("X · 중기", "최소 숙박 설정이 예약을 막음", ORANGE, "전략 ①"),
    6: ("X · 장기", "남부 이탈리아 방치 + 도시형", AQUA, "전략 ③"),
}
fig, ax = plt.subplots(figsize=(10, 5))
fig.subplots_adjust(left=0.01, right=0.99)
ax.set_xlim(0, 3); ax.set_ylim(0, 2.25); ax.axis("off")
for c, (axis_lab, desc, col, strat) in info.items():
    cx, cy = (c - 1) % 3, 1 - (c - 1) // 3
    face = col if col != GRAY else "#f3f2ee"
    ax.add_patch(mpl.patches.FancyBboxPatch((cx + 0.04, cy + 0.05), 0.92, 0.9, boxstyle="round,pad=0,rounding_size=0.04",
                                            facecolor=face, edgecolor="white", linewidth=2, alpha=0.16 if col != GRAY else 1))
    ax.add_patch(mpl.patches.FancyBboxPatch((cx + 0.04, cy + 0.05), 0.92, 0.9, boxstyle="round,pad=0,rounding_size=0.04",
                                            facecolor="none", edgecolor=col if col != GRAY else LIGHT, linewidth=2))
    ax.text(cx + 0.1, cy + 0.82, f"{c}번", fontsize=16, fontweight="bold", color=INK, va="top")
    ax.text(cx + 0.9, cy + 0.82, axis_lab, fontsize=10, color=INK2, va="top", ha="right")
    ax.text(cx + 0.1, cy + 0.55, f"{cnt[c]:,}건 ({cnt[c] / len(s):.1%})", fontsize=12, color=INK, va="center")
    ax.text(cx + 0.1, cy + 0.36, desc, fontsize=10, color=INK2, va="center")
    ax.text(cx + 0.1, cy + 0.15, strat, fontsize=10, fontweight="bold", color=col if col != GRAY else MUTED, va="center")
for i, lab in enumerate(["단기 (1–3박)", "중기 (4–29박)", "장기 (30박+)"]):
    ax.text(i + 0.5, 2.12, lab, ha="center", fontsize=12, fontweight="bold", color=INK2)
ax.set_title("2×3 세그먼트 — 최근 1년 리뷰 O/X × 최소 숙박", loc="left", pad=4)
save(fig, "04_cells_2x3.png", "source 0, 678,130건 · 겹침 0 · 미분류 0")

# ── 05. 동급 그룹 298개 — 중기 − 단기 무거래율 ──────────────────────
pg = u.groupby(["peer", "stay"])["norev"].agg(["mean", "size"]).unstack()
pg = pg[(pg[("size", "단기")] >= 30) & (pg[("size", "중기")] >= 30)]
diff = (pg[("mean", "중기")] - pg[("mean", "단기")]) * 100
k = int((diff > 0).sum())
fig, ax = plt.subplots(figsize=(8, 4))
edges = np.arange(np.floor(diff.min() / 4) * 4, diff.max() + 4, 4)
n_, e_, patches = ax.hist(diff, bins=edges, color=ORANGE, edgecolor="white", linewidth=1.5)
for p_, left in zip(patches, e_[:-1]):
    if left < 0:
        p_.set_facecolor(BLUE)
ax.axvline(0, color=INK2, lw=1.2)
ax.text(0.98, 0.92, f"{len(diff)}개 중 {k}개 ({k / len(diff):.0%})\n중기가 더 안 팔림", transform=ax.transAxes,
        ha="right", va="top", fontsize=13, fontweight="bold", color=ORANGE)
ax.text(0.02, 0.92, f"단기가 더 안 팔림\n{len(diff) - k}개", transform=ax.transAxes, ha="left", va="top", fontsize=10, color=BLUE)
ax.set_xlabel("같은 동급 그룹 안에서 (중기 무거래율 - 단기 무거래율), %p"); ax.set_ylabel("동급 그룹 수")
ax.set_title("같은 도시 · 같은 방 타입 · 같은 인원끼리 비교해도", loc="left")
save(fig, "05_peer_groups.png", f"동급 그룹 = 도시 × 방 타입 × 수용 인원, 단기·중기 각 30건 이상 · 차이 중앙값 +{diff.median():.1f}%p · 부호 검정 p < 0.001")

# ── 06. 로지스틱 회귀 용량-반응 (segmentation_2x3.ipynb 6-4 출력) ────
# 값은 노트북 6-4 출력 그대로 (reports/MIDSTAY_MIN_NIGHTS.md 2-2 표와 같다): 오즈비 · 95% 하한 · 95% 상한
order = ["1박", "2박", "3박", "4박", "5박", "6–7박", "8–29박"]
dose = pd.DataFrame([(0.995, 0.978, 1.012), (1, 1, 1), (1.470, 1.437, 1.504), (1.826, 1.765, 1.888),
                     (2.642, 2.549, 2.738), (4.002, 3.857, 4.153), (7.861, 7.492, 8.247)],
                    index=order, columns=["or", "lo", "hi"])
fig, ax = plt.subplots(figsize=(8, 4))
cols = [BLUE] * 3 + [ORANGE] * 4
bars = ax.bar(range(7), dose["or"], color=cols, width=0.62)
ax.errorbar(range(7), dose["or"], yerr=[dose["or"] - dose["lo"], dose["hi"] - dose["or"]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
for i, (v, hi) in enumerate(zip(dose["or"], dose["hi"])):
    ax.text(i, hi + 0.18, f"{v:.2f}" if i != 1 else "1 (기준)", ha="center", va="bottom", fontsize=10, color=INK)
ax.axhline(1, color=INK2, lw=1)
ax.set_xticks(range(7), order); ax.set_ylim(0, 9.2); ax.set_ylabel("무거래 오즈비 (2박 = 1)")
ax.set_title("가격 · 편의시설 · 지역을 맞춰도 하루 늘릴 때마다 더 안 팔린다", loc="left")
save(fig, "06_logit_dose.png", "로지스틱 회귀 · 585,601건 · 신규 매물 제외 · 지역 더미 포함 · 막대 끝은 95% 신뢰구간")


# ── 07–08. 같은 호스트 안 비교 ──────────────────────────────────────
def fe_lpm(df, y, xs, g):
    D = df[[y] + xs + [g]].dropna()
    dm = D[[y] + xs] - D.groupby(g)[[y] + xs].transform("mean")
    X, Y = dm[xs].to_numpy(float), dm[y].to_numpy(float)
    b = np.linalg.lstsq(X, Y, rcond=None)[0]
    e = Y - X @ b
    inv = np.linalg.inv(X.T @ X)
    G = pd.factorize(D[g])[0]
    S = np.zeros((G.max() + 1, len(xs)))
    np.add.at(S, G, X * e[:, None])
    se = np.sqrt(np.diag(inv @ (S.T @ S) @ inv))
    return pd.DataFrame({"b": b * 100, "lo": (b - 1.96 * se) * 100, "hi": (b + 1.96 * se) * 100}, index=xs)


both = u.groupby("host_id")["mid"].agg(["min", "max"])
both = both[(both["min"] == 0) & (both["max"] == 1)].index
hg = u[u["host_id"].isin(both)].groupby(["host_id", "stay"])["norev"].mean().unstack()
hd_ = hg["중기"] - hg["단기"]
kk, jj = int((hd_ > 0).sum()), int((hd_ < 0).sum())
fig, ax = plt.subplots(figsize=(6.4, 4))
bars = ax.bar([0, 1], [hg["단기"].mean() * 100, hg["중기"].mean() * 100], color=[BLUE, ORANGE], width=0.55)
bar_labels(ax, bars, lambda v: f"{v:.1f}%", size=13)
ax.set_xticks([0, 1], ["같은 호스트의\n단기 매물", "같은 호스트의\n중기 매물"]); ax.set_yticks([]); ax.set_ylim(0, 52)
ax.set_title("같은 사람이 올린 매물인데도", loc="left")
save(fig, "07_same_host_rates.png", f"단기·중기 매물을 둘 다 가진 호스트 {len(hg):,}명 · 차이가 난 호스트 중 {kk / (kk + jj):.0%}에서 중기가 더 안 팔림")

base = u[~u["new_listing"] & u["price_rel"].notna() & u["amenity_rel"].notna()]
hb = base[base["host_id"].isin(both)].copy()
DOSE = {"1박": (1, 1), "3박": (3, 3), "4박": (4, 4), "5박": (5, 5), "6–7박": (6, 7), "8–29박": (8, 29)}
for k_, (lo, hi) in DOSE.items():
    hb[k_] = hb["minimum_nights"].between(lo, hi).astype(int)
hdose = fe_lpm(hb, "norev", list(DOSE) + ["lpr", "a5", "entire"], "host_id").loc[list(DOSE)]
hdose.loc["2박"] = 0.0
hdose = hdose.reindex(order)
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(range(7), hdose["b"], color=[BLUE] * 3 + [ORANGE] * 4, width=0.62)
ax.errorbar(range(7), hdose["b"], yerr=[hdose["b"] - hdose["lo"], hdose["hi"] - hdose["b"]], fmt="none", ecolor=INK2, elinewidth=1, capsize=3)
for i, (v, hi) in enumerate(zip(hdose["b"], hdose["hi"])):
    ax.text(i, max(hi, 0) + 0.8, "기준" if i == 1 else f"{v:+.1f}%p", ha="center", va="bottom", fontsize=10, color=INK)
ax.axhline(0, color=INK2, lw=1)
ax.set_xticks(range(7), order); ax.set_ylim(-3, 37); ax.set_ylabel("무거래 확률 증가 (%p)")
ax.set_title("같은 호스트 안에서도 최소 숙박이 길수록 안 팔린다", loc="left")
save(fig, "08_within_host_dose.png", "호스트 더미를 넣은 선형회귀 · 가격·편의시설·통집 통제 · 2박 매물 무거래율 21.8% 기준 · 막대 끝은 95% 신뢰구간")

# ── 09. 편의시설이 좋아도 중기는 2배 ─────────────────────────────────
mm = base[base["host_is_superhost"].isin(["t", "f"])]          # 회귀와 같은 표본 (MIDSTAY 2-3 표와 같은 값)
ab = pd.cut(mm["amenity_rel"], [-np.inf, -12, -6, 0, 6, np.inf], labels=["-12개 이하", "-11 ~ -6", "-5 ~ 0", "+1 ~ +6", "+7개 이상"])
it = mm.groupby([ab, "stay"])["norev"].mean().unstack()[["단기", "중기"]] * 100
fig, ax = plt.subplots(figsize=(8, 4.2))
xs = np.arange(len(it))
for col, c in [("단기", BLUE), ("중기", ORANGE)]:
    ax.plot(xs, it[col], color=c, lw=2.2, marker="o", markersize=8, markeredgecolor="white", markeredgewidth=1.5)
    for xi, v in zip(xs, it[col]):
        ax.text(xi, v + (2.2 if col == "중기" else -4.6), f"{v:.0f}%", ha="center", fontsize=9.5, color=INK)
    ax.text(xs[-1] + 0.15, it[col].iloc[-1], col, color=c, fontsize=11, fontweight="bold", va="center")
ax.set_xticks(xs, it.index); ax.set_xlim(-0.3, len(it) - 0.4); ax.set_ylim(0, 68); ax.set_yticks([])
ax.set_xlabel("동급 대비 편의시설")
ax.set_title("편의시설이 좋아도 중기는 단기보다 약 2배 안 팔린다", loc="left")
save(fig, "09_amenity_interaction.png", "단기·중기 매물의 무거래율 (회귀와 같은 585,601건, 신규 매물 제외) · 상호작용 오즈비 0.985 — 편의시설과 최소 숙박은 따로 작용한다")

# ── 10. 끊김 비율 (과거에 팔렸던 매물 중 최근 1년 0건) ────────────────
ever = u[u["number_of_reviews"] > 0]
lb = ever.groupby(pd.cut(ever["minimum_nights"], [0, 1, 2, 3, 4, 5, 7, 29], labels=order))["norev"].mean() * 100
fig, ax = plt.subplots(figsize=(8, 4))
bars = ax.bar(range(7), lb.values, color=[BLUE] * 3 + [ORANGE] * 4, width=0.62)
bar_labels(ax, bars, lambda v: f"{v:.1f}%", pad=0.4)
ax.set_xticks(range(7), order); ax.set_yticks([]); ax.set_ylim(0, 36)
ax.set_title("팔리던 매물도 최소 숙박이 길면 더 자주 끊긴다", loc="left")
save(fig, "10_lapse_by_minnights.png", "끊김 비율 = 누적 리뷰가 있는 매물 중 최근 1년 리뷰 0건 · 중기 23.8% vs 단기 11.8% · 같은 호스트 안에서도 +8.0%p")

# ── 11. 2번 vs 1번 — 예약은 확실히 적고, 매출은 단정 불가 ─────────────
o = u[u["number_of_reviews_ltm"] > 0].copy()
o["nights"] = np.minimum(o["number_of_reviews_ltm"] / 0.5 * np.maximum(o["minimum_nights"], 3), 0.7 * 365)
o["revenue"] = o["nights"] * o["price"]
ob = o.groupby("host_id")["mid"].agg(["min", "max"])
oh = o[o["host_id"].isin(ob[(ob["min"] == 0) & (ob["max"] == 1)].index)]
res = {}
for v, name in [("number_of_reviews_ltm", "예약 수"), ("nights", "추정 숙박일"), ("revenue", "추정 연매출")]:
    g = o.groupby(["peer", "stay"])[v].agg(["median", "size"]).unstack()
    g = g[(g[("size", "단기")] >= 20) & (g[("size", "중기")] >= 20)]
    h = oh.groupby(["host_id", "stay"])[v].median().unstack()
    res[name] = ((g[("median", "중기")] / g[("median", "단기")]).median(), (h["중기"] / h["단기"]).median())
res = pd.DataFrame(res, index=["같은 동급 그룹", "같은 호스트"]).T
fig, ax = plt.subplots(figsize=(8, 4))
x = np.arange(len(res)); w = 0.36
for j, (col, c) in enumerate([("같은 동급 그룹", ORANGE), ("같은 호스트", GRAY)]):
    bars = ax.bar(x + (j - 0.5) * (w + 0.02), res[col], w, color=c, label=f"{col} 기준")
    bar_labels(ax, bars, lambda v: f"{v:.2f}배", pad=0.02)
ax.axhline(1, color=INK2, lw=1.2); ax.text(-0.42, 1.015, "1배 = 단기와 같음", fontsize=9, color=INK2, va="bottom", ha="left")
ax.set_xticks(x, res.index); ax.set_yticks([]); ax.set_ylim(0, 1.35)
ax.legend(frameon=False, loc="upper left", fontsize=10, ncol=2)
ax.set_title("2번은 예약이 확실히 적다 — 매출은 비교 기준에 따라 뒤집힌다", loc="left")
save(fig, "11_cell2_vs_short.png", "팔리는 매물끼리 중기 ÷ 단기 (중앙값) · 추정 숙박일은 손님이 최소 숙박만큼 묵는다고 가정 (중기에 유리)")

# ── 12. 기대 효과 — 5번 ─────────────────────────────────────────────
s["rev_year"] = s["price"] * s["occ_review"] * 365
q = s[(s.cell == 2) & (s.number_of_reviews_ltm > 0)]["rev_year"].quantile([.25, .5])
OFF = s.loc[s["quote_peak"].eq(False), "price_rel"].median() / s.loc[s["quote_peak"].eq(True), "price_rel"].median()
band = pd.cut(s["minimum_nights"], [0, 1, 2, 3, 4, 5, 7, 29, np.inf], labels=order + ["30박+"]).astype(str)
gain = (hdose["b"] - hdose.loc["3박", "b"]) / 100
c5 = s[(s["cell"] == 5) & ~s["new_listing"]]
conv_all = band[c5.index].map(gain).fillna(0).sum()
fig, ax = plt.subplots(figsize=(8, 3.6))
for i, adopt in enumerate([0.3, 0.5, 1.0]):
    lo_, hi_ = [conv_all * adopt * rv * OFF * 0.155 / 1e4 for rv in (q.iloc[0], q.iloc[1])]
    ax.plot([lo_, hi_], [i, i], color=ORANGE, lw=6, solid_capstyle="round", alpha=0.85)
    ax.text(hi_ + 6, i, f"{lo_:,.0f} – {hi_:,.0f}만 €", va="center", fontsize=11, color=INK)
    ax.text(-8, i, f"참여 {adopt:.0%}\n({conv_all * adopt:,.0f}건 전환)", va="center", ha="right", fontsize=10, color=INK2)
ax.set_yticks([]); ax.set_ylim(-0.6, 2.6); ax.set_xlim(-2, 470)
ax.grid(axis="x"); ax.grid(axis="y", visible=False); ax.set_xlabel("연 수수료 (만 €)")
ax.spines["bottom"].set_visible(False)
ax.set_title("5번이 3박 이하로 낮추면 — 연 수수료 증가 범위", loc="left")
save(fig, "12_impact_cell5.png", f"5번 중 신규 제외 {len(c5):,}건 · 같은 호스트 안 용량-반응 적용 · 전환 매물 매출 = 2번 하위 25%~중앙값 × {OFF:.2f}(비성수기 보정) · 수수료 15.5%")

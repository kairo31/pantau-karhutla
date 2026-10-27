"""Prakiraan jumlah titik panas BULANAN (1-6 bulan) untuk Sumatera, Kalimantan, Papua.

Dua model, strategi direct (satu model per horizon, tiga wilayah digabung):
  RF    : Random Forest pada anomali terhadap klimatologi bulan target (dari notebook pengguna).
  Ridge : regresi linear ter-regularisasi pada anomali yang sama. Linear, jadi bisa melampaui
          rentang data latih, yang tidak bisa dilakukan pohon (kelemahan RF di bulan puncak).
  Ens   : rata-rata RF dan Ridge pada skala log.

Perbaikan dari notebook: indeks Nino/DMI yang terlambat terbit di-forward-fill (maks. 6 bulan) pada
bulan asal, bukan diisi -99 (nilai yang tak pernah ada saat latihan). Jumlah bulan yang diisi
dilaporkan di keluaran. Bulan berjalan (belum lengkap) dilaporkan terpisah sebagai 'aktual sejauh ini'
dan tidak dipakai untuk latihan.

Pakai:  python scripts/forecast_monthly.py [--backtest]
Tanpa --backtest, hasil backtest lama di docs/data/forecast_monthly.json dipakai ulang.
"""
import argparse, json, warnings
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import DATA, OUT, load_index

warnings.filterwarnings("ignore")

REGIONS = ["Sumatera", "Kalimantan", "Papua"]
HORIZONS = [1, 2, 3, 4, 5, 6]
START = "2012-08-01"
BACKTEST_FROM = "2019-01-01"
BACKTEST_STEP = 3
RF_PARAMS = dict(min_samples_leaf=3, max_features=0.5, random_state=0, n_jobs=-1)
N_TREES, N_TREES_BT = 300, 150
RAIN_COLS = [6, 7, 8]
MAX_FFILL = 6
MODELS = ["RF", "Ridge", "Ens"]
LABELS = {"RF": "Random Forest", "Ridge": "Ridge (linear)", "Ens": "Rata-rata RF + Ridge"}
PEAK_Q = 0.9


def load():
    d = pd.read_csv(DATA / "daily.csv", parse_dates=["acq_date"])
    d = d[d.wilayah.isin(REGIONS)]
    r = pd.read_csv(DATA / "rain_daily.csv", parse_dates=["tanggal"])
    return d, r


class Ctx:
    def __init__(self, d, r):
        last = d.acq_date.max()
        full = last == last + pd.offsets.MonthEnd(0)
        end = last.to_period("M").to_timestamp()
        if not full:
            end -= pd.offsets.MonthBegin(1)
        self.last_day, self.partial = last, not full
        self.M = pd.date_range(START, end, freq="MS")
        self.n = len(self.M)
        M = self.M
        mo = d.assign(b=d.acq_date.dt.to_period("M").dt.to_timestamp()).groupby(["b", "wilayah"]).titik.sum()
        ro = r.assign(b=r.tanggal.dt.to_period("M").dt.to_timestamp()).groupby(["b", "wilayah"]).hujan_mm.sum()
        self.Y = {w: np.log1p(mo.xs(w, level="wilayah").reindex(M, fill_value=0)) for w in REGIONS}
        self.R = {}
        for w in REGIONS:
            s = ro.xs(w, level="wilayah").reindex(M) if w in ro.index.get_level_values(1) else pd.Series(np.nan, index=M)
            self.R[w] = np.log(s.where(s > 0))
        nino, dmi = load_index("nino34"), load_index("dmi")
        nino, dmi = nino.where(nino > -90), dmi.where(dmi > -90)
        self.nino_last = None if nino.dropna().empty else nino.dropna().index.max()
        self.dmi_last = None if dmi.dropna().empty else dmi.dropna().index.max()
        N, D = nino.reindex(M), dmi.reindex(M)
        gap = lambda last: None if last is None else max(0, int(self.M[-1].to_period("M").ordinal - last.to_period("M").ordinal))
        self.filled = {"nino": gap(self.nino_last), "dmi": gap(self.dmi_last)}
        self.N, self.D = N.ffill(limit=MAX_FFILL), D.ffill(limit=MAX_FFILL)

    def feats(self, w, t, h):
        y, r, N, D, M = self.Y[w], self.R[w], self.N, self.D, self.M
        tm = (M[t].month - 1 + h) % 12 + 1
        f = [y.iloc[t], y.iloc[t - 1], y.iloc[t - 2], y.iloc[t - 3:t + 1].mean(),
             y.iloc[t + h - 12] if t + h - 12 >= 0 else np.nan,
             y.iloc[t + h - 24] if t + h - 24 >= 0 else np.nan,
             r.iloc[t], r.iloc[t - 2:t + 1].mean(), r.iloc[t - 5:t + 1].mean(),
             N.iloc[t], N.iloc[t - 2], N.iloc[t - 5:t + 1].mean(),
             D.iloc[t], D.iloc[t - 2], D.iloc[t - 5:t + 1].mean(),
             np.sin(2 * np.pi * tm / 12), np.cos(2 * np.pi * tm / 12)]
        f += [int(w == k) for k in REGIONS]
        f += [N.iloc[t - 2:t + 1].mean(), N.iloc[t - 5:t + 1].max(), D.iloc[t - 2:t + 1].mean(),
              D.iloc[t - 5:t + 1].max(), N.iloc[t] * D.iloc[t], N.iloc[t] - N.iloc[t - 3]]
        hist = y.iloc[:t + 1]
        f += [hist[hist.index.month == tm].mean()]
        return f

    def dataset(self, h):
        X, y, T, W = [], [], [], []
        for w in REGIONS:
            for t in range(24, self.n - h):
                f = self.feats(w, t, h)
                if np.isnan(np.delete(np.array(f, float), RAIN_COLS)).any():
                    continue
                X.append(f); y.append(self.Y[w].iloc[t + h]); T.append(t); W.append(w)
        return np.array(X, float), np.array(y), np.array(T), np.array(W)


def fit_rf(X, y, n_trees):
    return RandomForestRegressor(n_estimators=n_trees, **RF_PARAMS).fit(np.nan_to_num(X, nan=-99.0), y - X[:, -1])


def pred_rf(m, X):
    return m.predict(np.nan_to_num(X, nan=-99.0)) + X[:, -1]


def fit_ridge(X, y):
    m = make_pipeline(SimpleImputer(strategy="mean", add_indicator=True), StandardScaler(), Ridge(alpha=30.0))
    return m.fit(X, y - X[:, -1])


def pred_ridge(m, X):
    return m.predict(X) + X[:, -1]


def fit_all(X, y, n_trees):
    return fit_rf(X, y, n_trees), fit_ridge(X, y)


def predict_all(ms, X):
    rf, rd = pred_rf(ms[0], X), pred_ridge(ms[1], X)
    out = {"RF": rf, "Ridge": rd, "Ens": (rf + rd) / 2}
    return {k: np.clip(v, 0, np.log1p(5e5)) for k, v in out.items()}


def metrics(a, p):
    a, p = np.asarray(a), np.asarray(p)
    e = p - a
    return {"mae_log": float(np.abs(e).mean()), "bias_log": float(e.mean()),
            "dalam_2x": float((np.abs(e) <= np.log(2)).mean()), "n": int(len(a))}


def backtest(ctx, data):
    i0 = ctx.M.get_loc(pd.Timestamp(BACKTEST_FROM)) - 1
    rows = []
    for h in HORIZONS:
        X, y, T, W = data[h]
        for t in range(i0, ctx.n - h, BACKTEST_STEP):
            tr, te = (T + h) <= t, T == t
            if te.sum() == 0:
                continue
            P = predict_all(fit_all(X[tr], y[tr], N_TREES_BT), X[te])
            for k, w in enumerate(W[te]):
                rows.append(dict(w=w, h=h, a=y[te][k], naive=X[te][k, 4], clim=X[te][k, -1], **{m: P[m][k] for m in MODELS}))
        print(f"backtest h={h} selesai", flush=True)
    return pd.DataFrame(rows)


def summarize_bt(bt):
    """Skema keluaran dibaca docs/assets/app.js (renderMonthly)."""
    nav = metrics(bt.a, bt.naive)["mae_log"]
    thr = bt.a.quantile(PEAK_Q)
    pk = bt[bt.a >= thr]
    cols = MODELS + ["clim", "naive"]
    names = {"clim": "Klimatologi", "naive": "SeasonalNaive"}
    out = {"n": int(len(bt)), "peak": {"threshold": float(np.expm1(thr)), "ratio": {}},
           "overall": {}, "by_h": {}, "detail": {}, "q": {}}
    for c in cols:
        k = names.get(c, c)
        out["by_h"][k] = {str(h): float((g[c] - g.a).abs().mean()) for h, g in bt.groupby("h")}
    for m in MODELS:
        tot = metrics(bt.a, bt[m])
        out["overall"][m] = {**tot, "skill": 1 - tot["mae_log"] / nav}
        out["peak"]["ratio"][m] = {str(h): float(np.expm1(g[m].clip(lower=0)).sum() / np.expm1(g.a).sum()) for h, g in pk.groupby("h")}
        out["detail"][m] = {"peak_mae_log": float((pk[m] - pk.a).abs().mean()), "peak_bias_log": float((pk[m] - pk.a).mean()),
                            "by_h": {str(h): metrics(g.a, g[m]) for h, g in bt.groupby("h")}}
        out["q"][m] = {str(h): [float(v) for v in (g.a - g[m]).quantile([.1, .9]).values] for h, g in bt.groupby("h")}
    out["overall"]["Klimatologi"] = {"mae_log": float((bt.clim - bt.a).abs().mean())}
    out["overall"]["SeasonalNaive"] = {"mae_log": nav}
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--backtest", action="store_true")
    args = ap.parse_args()
    d, r = load()
    ctx = Ctx(d, r)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "forecast_monthly.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    data = {h: ctx.dataset(h) for h in HORIZONS}

    if args.backtest or not old.get("backtest") or "overall" not in old["backtest"]:
        bt = summarize_bt(backtest(ctx, data))
    else:
        bt = old["backtest"]

    t_now = ctx.n - 1
    fc = {m: {w: [] for w in REGIONS} for m in MODELS}
    for h in HORIZONS:
        X, y, _, _ = data[h]
        ms = fit_all(X, y, N_TREES)
        Xn = np.array([ctx.feats(w, t_now, h) for w in REGIONS], float)
        P = predict_all(ms, Xn)
        mon = str((ctx.M[t_now] + pd.DateOffset(months=h)).date())
        for m in MODELS:
            lo_q, hi_q = bt["q"][m][str(h)]
            for k, w in enumerate(REGIONS):
                p = P[m][k]
                fc[m][w].append({"bulan": mon[:7], "h": h, "p": float(np.expm1(p)),
                                 "lo": float(np.expm1(max(p + lo_q, 0))), "hi": float(np.expm1(p + hi_q))})

    # aktual sejauh ini pada bulan berjalan (tidak lengkap): dilaporkan terpisah, tidak dipakai latihan
    mtd = None
    if ctx.partial:
        m0 = ctx.last_day.to_period("M").to_timestamp()
        sub = d[d.acq_date >= m0]
        dim, nd = int(m0.days_in_month), int(ctx.last_day.day)
        mtd = {w: {"bulan": str(m0.date())[:7], "hari": nd, "hari_dalam_bulan": dim, "tanggal_terakhir": str(ctx.last_day.date()),
                   "sejauh_ini": int(sub[sub.wilayah == w].titik.sum()),
                   "proyeksi_laju": float(sub[sub.wilayah == w].titik.sum() / nd * dim)} for w in REGIONS}

    hist = {w: {"bulan": [str(m.date())[:7] for m in ctx.M if m >= pd.Timestamp("2015-01-01")],
                "titik": [float(np.expm1(v)) for m, v in ctx.Y[w].items() if m >= pd.Timestamp("2015-01-01")]} for w in REGIONS}
    stale = [v for v in ctx.filled.values() if v is not None]
    res = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof_month": str(ctx.M[-1].date())[:7],
           "last_day": str(ctx.last_day.date()),
           "labels": {**LABELS, "Klimatologi": "Klimatologi bulan", "SeasonalNaive": "Bulan sama tahun lalu"},
           "regions": REGIONS, "horizons": HORIZONS, "ffill_bulan_indeks": max(stale) if stale else 0,
           "ffill_detail": ctx.filled, "mtd": mtd, "history": hist, "forecast": fc, "backtest": bt}
    path.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    print("OK", path, "| asof", res["asof_month"], "| indeks ENSO diisi (bulan):", ctx.filled)
    for m in MODELS:
        print(m, {w: round(fc[m][w][0]["p"]) for w in REGIONS}, "bulan", fc[m][REGIONS[0]][0]["bulan"][:7])
    if mtd:
        print("Aktual sejauh ini:", {w: mtd[w]["sejauh_ini"] for w in REGIONS})


if __name__ == "__main__":
    main()

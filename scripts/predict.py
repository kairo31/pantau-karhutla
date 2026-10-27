"""Model peluang akhir musim karhutla (nasional) -> docs/data/prediction.json

Pada hari t, berapa peluang rata-rata 14 hari titik panas nasional turun di bawah ambang TH
(dan bertahan 14 hari) dalam h hari ke depan? Regresi logistik per (ambang, horizon), diuji
leave-one-year-out. Tiga model: A (hanya tanggal), B (kondisi api), C (B + ENSO + hujan).

Pemakaian:
  python scripts/predict.py                  # prediksi per hari lengkap terakhir
  python scripts/predict.py --backtest       # hitung ulang validasi (lebih lama)
  python scripts/predict.py --asof 2026-10-23
"""
import argparse, json, os, sys, warnings
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, OUT, load_index, national_series, read_daily
warnings.filterwarnings("ignore")

HORIZONS = [7, 14, 21, 28, 35, 42, 49, 56, 63, 70]
BT_HORIZONS = [7, 14, 21, 28, 42, 56]
THRESHOLDS = [1000, 500]
WIN = ("09-15", "12-15")                    # jendela model (bulan-hari)
N_BOOT = 100
SETS = {
    "A": ["doy"],
    "B": ["lvl", "ratio", "trend", "dsp", "cum", "doy"],
    "C": ["lvl", "ratio", "trend", "dsp", "cum", "doy", "nino", "rain"],
}
LABEL = {"A": "A. Hanya kalender (pembanding)",
         "B": "B. Kondisi api (utama)",
         "C": "C. Kondisi api + ENSO + hujan"}


class Ctx:
    def __init__(self, asof=None):
        daily = read_daily()
        last = pd.Timestamp(daily.acq_date.max())
        self.asof = pd.Timestamp(asof) if asof else last
        self.nas = national_series(daily, self.asof)
        self.sm = self.nas.rolling(14, min_periods=7).mean()
        nino = load_index("nino34")
        rain_p = DATA / "rain_daily.csv"
        rn = pd.read_csv(rain_p, parse_dates=["tanggal"]) if rain_p.exists() else pd.DataFrame()
        if len(rn):
            rn = rn[rn.wilayah.isin(["Kalimantan", "Sumatera"])].groupby("tanggal").hujan_mm.mean()
        self.static = {}
        for y in range(2012, self.asof.year + 1):
            jj = nino[f"{y}-06-01":f"{y}-07-01"].mean() if len(nino) else np.nan
            ra = rn[f"{y}-08-01":f"{y}-09-30"] if len(rn) else pd.Series(dtype=float)
            self.static[y] = dict(nino=jj, rain=ra.mean() if len(ra) >= 55 else np.nan)
        self.years = [y for y in range(2012, self.asof.year)]      # musim yang sudah lengkap

    def end_date(self, y, th):
        pk = self.sm[f"{y}-08-01":f"{y}-12-31"].idxmax()
        after = self.sm[pk:f"{y+1}-03-31"]
        run = (after < th).rolling(14).sum()
        hit = run[run == 14]
        return (hit.index[0] - pd.Timedelta(days=13)) if len(hit) else pd.NaT

    def feats(self, t):
        y = t.year
        seg = self.sm[f"{y}-08-01":t]
        pk = seg.max()
        lvl = np.log1p(self.sm[t])
        prev = self.sm.get(t - pd.Timedelta(days=7), np.nan)
        return dict(lvl=lvl, ratio=self.sm[t] / pk if pk > 0 else np.nan,
                    trend=lvl - np.log1p(prev), dsp=(t - seg.idxmax()).days,
                    cum=np.log1p(self.nas[f"{y}-08-01":t].sum()),
                    doy=(t - pd.Timestamp(y, 9, 1)).days,
                    nino=self.static[y]["nino"], rain=self.static[y]["rain"])

    def build(self, th):
        rows = []
        for y in self.years:
            e = self.end_date(y, th)
            for t in pd.date_range(f"{y}-{WIN[0]}", f"{y}-{WIN[1]}"):
                if t not in self.sm.index or np.isnan(self.sm[t]) or self.sm[t] < th:
                    continue
                if pd.notna(e) and t >= e:
                    continue                        # sudah berakhir: tidak lagi "berisiko"
                f = self.feats(t); f.update(year=y, t=t)
                for h in HORIZONS:
                    f[f"y{h}"] = int(pd.notna(e) and e <= t + pd.Timedelta(days=h))
                rows.append(f)
        return pd.DataFrame(rows)


def mk():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))


def median_date(asof, hs, ps):
    """Tanggal ketika peluang kumulatif melewati 0,5 (interpolasi linear), atau None."""
    xs, ys = [0] + list(hs), [0.0] + list(ps)
    for i in range(1, len(xs)):
        if ys[i] >= 0.5:
            f = (0.5 - ys[i - 1]) / max(ys[i] - ys[i - 1], 1e-9)
            return (asof + pd.Timedelta(days=round(xs[i - 1] + f * (xs[i] - xs[i - 1])))).strftime("%Y-%m-%d")
    return None


def backtest(df, th):
    res = {m: {} for m in SETS}
    for h in BT_HORIZONS:
        ref = None
        d = df.dropna(subset=SETS["C"])
        for name, cols in SETS.items():
            ps = pd.Series(index=d.index, dtype=float)
            for y in d.year.unique():
                tr, te = d[d.year != y], d[d.year == y]
                yt = tr[f"y{h}"]
                if yt.nunique() < 2:
                    ps[te.index] = yt.mean(); continue
                ps[te.index] = mk().fit(tr[cols], yt).predict_proba(te[cols])[:, 1]
            b = float(np.mean((d[f"y{h}"] - ps) ** 2))
            if name == "A": ref = b
            res[name][str(h)] = {"brier": round(b, 4), "skill": round(1 - b / ref, 3) if ref else 0.0}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof"); ap.add_argument("--backtest", action="store_true")
    a = ap.parse_args()
    ctx = Ctx(a.asof)
    asof = ctx.asof
    OUT.mkdir(parents=True, exist_ok=True)
    pj = OUT / "prediction.json"
    old = json.loads(pj.read_text()) if pj.exists() else {}
    out = {"asof": asof.strftime("%Y-%m-%d"), "level": None, "peak_so_far": None, "status": "ok",
           "window": list(WIN), "labels": LABEL, "horizons": HORIZONS, "thresholds": {}}

    lvl = float(ctx.sm[asof]) if not np.isnan(ctx.sm[asof]) else None
    out["level"] = None if lvl is None else round(lvl)
    seg = ctx.sm[f"{asof.year}-08-01":asof]
    out["peak_so_far"] = round(float(seg.max())) if len(seg.dropna()) else None
    md = asof.strftime("%m-%d")
    if not (WIN[0] <= md <= WIN[1]):
        out["status"] = "di_luar_jendela"
        out["note"] = f"Model hanya berlaku untuk tanggal {WIN[0]} sampai {WIN[1]} (bulan-hari)."

    bt_old = old.get("backtest", {})
    out["backtest"] = bt_old
    out["analogs"] = {}
    for th in THRESHOLDS:
        df = ctx.build(th)
        t = {"n_rows": int(len(df)), "n_years": int(df.year.nunique()) if len(df) else 0, "models": {},
             "already_below": bool(lvl is not None and lvl < th)}
        if a.backtest or str(th) not in bt_old:
            print(f"Backtest ambang {th} ...")
            out["backtest"][str(th)] = backtest(df, th) if len(df) > 50 else {}
        # analog: nilai pada tanggal kalender yang sama di tahun-tahun lalu
        ana = []
        for y in ctx.years:
            try:
                tt = pd.Timestamp(y, asof.month, asof.day)
                e = ctx.end_date(y, th)
                lv = float(ctx.sm[tt])
                ana.append({"year": y, "level": round(lv), "end": None if pd.isna(e) else e.strftime("%Y-%m-%d"),
                            "days_left": None if pd.isna(e) else (e - tt).days})
            except Exception:
                pass
        out["analogs"][str(th)] = ana
        if out["status"] == "ok" and lvl is not None and lvl >= th and len(df) > 50:
            f = pd.DataFrame([ctx.feats(asof)])
            for name, cols in SETS.items():
                d = df.dropna(subset=cols)
                if f[cols].isna().any(axis=None) or d.year.nunique() < 5:
                    continue
                ps, lo, hi, rng, ys = [], [], [], np.random.default_rng(0), d.year.unique()
                for h in HORIZONS:
                    yt = d[f"y{h}"]
                    p = float(mk().fit(d[cols], yt).predict_proba(f[cols])[0, 1]) if yt.nunique() > 1 else float(yt.mean())
                    bs = []
                    for _ in range(N_BOOT):
                        tr = pd.concat([d[d.year == v] for v in rng.choice(ys, len(ys))])
                        if tr[f"y{h}"].nunique() > 1:
                            bs.append(float(mk().fit(tr[cols], tr[f"y{h}"]).predict_proba(f[cols])[0, 1]))
                    ps.append(round(p, 3))
                    lo.append(round(float(np.percentile(bs, 10)), 3) if bs else None)
                    hi.append(round(float(np.percentile(bs, 90)), 3) if bs else None)
                t["models"][name] = {"p": ps, "p10": lo, "p90": hi, "median_date": median_date(asof, HORIZONS, ps)}
        out["thresholds"][str(th)] = t

    pj.write_text(json.dumps(out, separators=(",", ":")))
    print(f"prediction.json: asof {out['asof']}, level {out['level']}, status {out['status']}")

    # riwayat prediksi (satu baris per hari per ambang), untuk melihat bagaimana perkiraan berubah
    hist_p = DATA / "prediction_history.csv"
    hist = pd.read_csv(hist_p) if hist_p.exists() else pd.DataFrame(columns=["asof", "ambang", "model", "median_date", "level"])
    new = [(out["asof"], int(th), m, v["median_date"], out["level"])
           for th, tv in out["thresholds"].items() for m, v in tv["models"].items()]
    if new:
        nd = pd.DataFrame(new, columns=hist.columns)
        hist = pd.concat([hist[hist["asof"] != out["asof"]], nd]).sort_values(["asof", "ambang", "model"])
        hist.to_csv(hist_p, index=False)


if __name__ == "__main__":
    main()

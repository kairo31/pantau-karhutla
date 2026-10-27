"""Bangun berkas JSON untuk situs (docs/data/*) dari data/*.csv."""
import json, os, sys, warnings
from datetime import datetime, timezone
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from common import DATA, OUT, REGION_ORDER, load_index, read_daily

START = "2012-01-20"
warnings.filterwarnings("ignore", category=DeprecationWarning)


def dump(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, separators=(",", ":"), allow_nan=False))


def nn(a, nd=0):
    """Array -> list dengan NaN menjadi None."""
    out = []
    for v in a:
        out.append(None if v is None or (isinstance(v, float) and np.isnan(v)) else (int(round(v)) if nd == 0 else round(float(v), nd)))
    return out


def season_row(sm, tot, y, asof):
    seg = sm[f"{y}-08-01":f"{y}-12-31"].dropna()
    if seg.empty or seg.max() <= 0:
        return None
    pk, pv = seg.idxmax(), float(seg.max())
    after = sm[pk:f"{y+1}-06-30"]
    run = (after < 0.2 * pv).rolling(14).sum()
    hit = run[run == 14]
    end = (hit.index[0] - pd.Timedelta(days=13)) if len(hit) else None
    return {"y": y, "peak": pk.strftime("%Y-%m-%d"), "peakv": round(pv),
            "total": int(tot[f"{y}-07-01":f"{y}-12-31"].sum()),
            "end": end.strftime("%Y-%m-%d") if end is not None and end <= asof else None,
            "ongoing": bool(y == asof.year)}


def main():
    daily = read_daily()
    asof = pd.Timestamp(daily.acq_date.max())
    idx = pd.date_range(START, asof)
    regions = [r for r in REGION_ORDER if r == "Nasional" or r in set(daily.wilayah)]
    series, seasons = {}, {}
    for r in regions:
        x = daily if r == "Nasional" else daily[daily.wilayah == r]
        g = x.groupby("acq_date").agg(n=("titik", "sum"), f=("frp", "sum"))
        g.index = pd.to_datetime(g.index)
        g = g.reindex(idx)
        series[r] = {"n": nn(g.n.values), "f": nn(g.f.values)}
        sm = g.n.rolling(14, min_periods=7).mean()
        rows = [season_row(sm, g.n, y, asof) for y in range(2012, asof.year + 1)]
        seasons[r] = [s for s in rows if s]
    dump("series.json", {"start": START, "last": asof.strftime("%Y-%m-%d"), "regions": regions, "data": series})
    dump("seasons.json", seasons)

    # hujan
    rp = DATA / "rain_daily.csv"
    rain = {"last": None, "stage_last": None, "regions": {}}
    if rp.exists():
        r = pd.read_csv(rp, parse_dates=["tanggal"])
        rain["last"] = r.tanggal.max().strftime("%Y-%m-%d")
        rain["prelim_days"] = int((r.groupby("tanggal").stage.first() == "prelim").sum())
        for reg, g in r.groupby("wilayah"):
            s = g.set_index("tanggal").hujan_mm
            rain["regions"][reg] = {}
            for y in range(2012, r.tanggal.max().year + 1):
                v = s.reindex(pd.date_range(f"{y}-07-01", f"{y}-12-31"))
                rain["regions"][reg][str(y)] = nn(v.values, 2)
    dump("rain.json", rain)

    # ENSO
    nino, dmi = load_index("nino34"), load_index("dmi")
    months = pd.date_range("2012-01-01", "2026-12-01", freq="MS")
    def mv(s): return nn(s.reindex(months).values, 2) if len(s) else [None] * len(months)
    dump("enso.json", {"start": "2012-01", "nino": mv(nino), "dmi": mv(dmi),
                       "nino_last": nino.dropna().index.max().strftime("%Y-%m") if len(nino.dropna()) else None,
                       "dmi_last": dmi.dropna().index.max().strftime("%Y-%m") if len(dmi.dropna()) else None})

    hist_p = DATA / "prediction_history.csv"
    hist = pd.read_csv(hist_p).to_dict("records") if hist_p.exists() else []
    for h in hist:
        h["median_date"] = None if pd.isna(h["median_date"]) else h["median_date"]
    dump("prediction_history.json", hist)
    dump("meta.json", {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                       "asof": asof.strftime("%Y-%m-%d"), "regions": regions})
    print("data situs dibangun; asof", asof.date(), "| wilayah", len(regions))


if __name__ == "__main__":
    main()

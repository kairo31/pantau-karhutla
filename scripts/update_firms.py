"""Tarik titik panas VIIRS SNPP dari API NASA FIRMS, perbarui data/daily.csv
dan buat grid peta 7 hari terakhir (docs/data/recent_grid.json).

Pemakaian:
  FIRMS_MAP_KEY=xxxx python scripts/update_firms.py
  python scripts/update_firms.py --backfill-from 2026-10-24   # isi celah
  python scripts/update_firms.py --sp-refresh                 # ganti NRT dgn data final (SP)
"""
import argparse, io, json, os, sys, time
from datetime import date, datetime, timedelta, timezone
import pandas as pd, numpy as np, requests
sys.path.insert(0, os.path.dirname(__file__))
from common import AREA, OUT, assign_region, read_daily, write_daily

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SOURCE_NRT = "VIIRS_SNPP_NRT"
SOURCE_SP = "VIIRS_SNPP_SP"
GRID = 0.1
EMPTY_COLS = ["latitude", "longitude", "acq_date", "confidence", "frp"]


def fetch(key: str, source: str, start: date, ndays: int, retries: int = 3) -> pd.DataFrame:
    """Satu panggilan API: ndays (1-10) hari mulai `start`."""
    url = f"{API}/{key}/{source}/{AREA}/{ndays}/{start:%Y-%m-%d}"
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, timeout=180)
            last = r.status_code
            text = r.text
            if r.status_code == 200 and text.startswith("latitude"):
                return pd.read_csv(io.StringIO(text))
            if r.status_code == 200 and not text.strip():
                return pd.DataFrame(columns=EMPTY_COLS)      # tidak ada data pada rentang itu
            snippet = text[:120].replace(key, "***")
            print(f"  percobaan {i+1}: HTTP {r.status_code} {snippet!r}", file=sys.stderr)
        except requests.RequestException as e:
            last = type(e).__name__
            print(f"  percobaan {i+1}: {last}", file=sys.stderr)
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"FIRMS gagal untuk {start} (+{ndays} hari), status terakhir: {last}")


def fetch_range(key, source, start: date, end: date) -> pd.DataFrame:
    frames, d = [], start
    while d <= end:
        n = min(10, (end - d).days + 1)
        frames.append(fetch(key, source, d, n))
        d += timedelta(days=n)
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True).drop_duplicates() if frames else pd.DataFrame(columns=EMPTY_COLS)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Hanya keyakinan nominal (n) dan tinggi (h); beri wilayah."""
    if df.empty:
        return df.assign(wilayah=[])
    df = df[df["confidence"].astype(str).str.lower().isin(["n", "h"])].copy()
    df["wilayah"] = assign_region(df.latitude.values, df.longitude.values)
    return df


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["acq_date", "wilayah", "titik", "frp"])
    return (df.groupby(["acq_date", "wilayah"], as_index=False)
              .agg(titik=("frp", "size"), frp=("frp", "sum")))


def merge_daily(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Timpa semua baris pada tanggal yang ada di `new` (data NRT hari terakhir bisa berubah)."""
    if new.empty:
        return old
    dates = set(new.acq_date.unique())
    keep = old[~old.acq_date.isin(dates)]
    return pd.concat([keep, new], ignore_index=True)


def build_grid(df: pd.DataFrame, dates: list) -> dict:
    """Agregasi sel 0,1 derajat per hari untuk peta: [lat, lon, titik_per_hari[], frp_per_hari[]]."""
    idx = {d: i for i, d in enumerate(dates)}
    df = df[df.acq_date.isin(idx)].copy()
    out = []
    if len(df):
        df["gy"] = np.floor(df.latitude / GRID).astype(int)
        df["gx"] = np.floor(df.longitude / GRID).astype(int)
        for (gy, gx), g in df.groupby(["gy", "gx"]):
            counts, frps = [0] * len(dates), [0] * len(dates)
            for d, sub in g.groupby("acq_date"):
                counts[idx[d]] = int(len(sub)); frps[idx[d]] = int(round(sub.frp.sum()))
            out.append([round((gy + .5) * GRID, 2), round((gx + .5) * GRID, 2), counts, frps])
    return {"cell": GRID, "dates": dates, "cells": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-from", help="YYYY-MM-DD: ambil ulang mulai tanggal ini")
    ap.add_argument("--sp-refresh", action="store_true", help="ganti data NRT lama dengan data final (SP)")
    ap.add_argument("--today", help="(uji) tanggal UTC hari ini")
    a = ap.parse_args()

    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        sys.exit("FIRMS_MAP_KEY belum diatur (GitHub: Settings > Secrets and variables > Actions).")

    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)       # hari UTC terakhir yang sudah lengkap
    daily = read_daily()
    last = date.fromisoformat(daily.acq_date.max()) if len(daily) else date(2012, 1, 20)

    # ambil ulang 7 hari terakhir (data NRT hari-hari terakhir bisa direvisi); isi celah bila ada
    start = min(yesterday - timedelta(days=6), last - timedelta(days=2))
    if a.backfill_from:
        start = min(start, date.fromisoformat(a.backfill_from))
    start = max(start, yesterday - timedelta(days=60))   # NRT hanya menyimpan sekitar 2 bulan
    print(f"Mengambil {SOURCE_NRT}: {start} .. {yesterday}")
    raw = clean(fetch_range(key, SOURCE_NRT, start, yesterday))
    new = summarize(raw)
    print(f"  {len(raw)} titik, tanggal {new.acq_date.min() if len(new) else '-'} .. "
          f"{new.acq_date.max() if len(new) else '-'}")
    daily = merge_daily(daily, new)

    if a.sp_refresh:                                     # data final (SP) tertinggal sekitar 2-3 bulan
        s, e = today - timedelta(days=150), today - timedelta(days=30)
        try:
            print(f"Menyegarkan dengan {SOURCE_SP}: {s} .. {e}")
            sp = summarize(clean(fetch_range(key, SOURCE_SP, s, e)))
            print(f"  {sp.acq_date.nunique() if len(sp) else 0} tanggal SP tersedia")
            daily = merge_daily(daily, sp)
        except Exception as ex:                          # tidak fatal
            print(f"PERINGATAN: refresh SP gagal: {ex}", file=sys.stderr)

    write_daily(daily)

    # grid peta 7 hari terakhir (hanya hari lengkap)
    gd = [(yesterday - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    grid = build_grid(raw, gd)
    grid["asof"] = gd[-1]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "recent_grid.json").write_text(json.dumps(grid, separators=(",", ":")))
    print(f"daily.csv: {len(daily)} baris, sampai {daily.acq_date.max()}; grid {len(grid['cells'])} sel")


if __name__ == "__main__":
    main()

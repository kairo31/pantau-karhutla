"""Perbarui data/rain_daily.csv: curah hujan harian CHIRPS v3 (rata-rata kotak wilayah).

Memakai produk final bila sudah terbit, jika belum memakai produk prelim.
Hari yang belum terbit dilewati dan dicoba lagi pada hari berikutnya.
Pemakaian: python scripts/update_rain.py [--from-date 2026-10-01]
"""
import argparse, os, sys
from datetime import date, datetime, timedelta, timezone
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from common import BBOX, DATA, RAIN_REGIONS

STAGES = [("final", "rnl"), ("prelim", "sat")]
REFETCH_DAYS = 30        # ambil ulang 30 hari terakhir agar prelim -> final


def get_day(day: date):
    """Kembalikan (DataArray 2D, stage) atau (None, None) bila belum terbit."""
    from dhis2eo.data.chc.chirps3 import daily           # impor lambat agar uji tidak butuh paketnya
    for stage, flavor in STAGES:
        try:
            ds = daily.fetch_day(day, BBOX, "precip", stage, flavor)
            return ds["precip"].isel(time=0), stage
        except Exception:
            continue
    return None, None


def region_means(da) -> dict:
    ydim = "y" if "y" in da.dims else "latitude"
    xdim = "x" if "x" in da.dims else "longitude"
    la, lo = da[ydim], da[xdim]
    out = {}
    for name, (x0, x1, y0, y1) in RAIN_REGIONS.items():
        m = (lo >= x0) & (lo <= x1) & (la >= y0) & (la <= y1)
        v = da.where(m).where(da >= 0).mean(skipna=True)
        out[name] = float(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-date")
    ap.add_argument("--today")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
    p = DATA / "rain_daily.csv"
    old = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["tanggal", "wilayah", "hujan_mm", "stage"])
    last = date.fromisoformat(old.tanggal.max()) if len(old) else date(2012, 7, 1)
    start = date.fromisoformat(a.from_date) if a.from_date else last - timedelta(days=REFETCH_DAYS)
    rows, got, missing = [], 0, 0
    d = start
    while d < today:                                     # sampai kemarin
        da, stage = get_day(d)
        if da is None:
            missing += 1
        else:
            got += 1
            for r, v in region_means(da).items():
                if not np.isnan(v):
                    rows.append((d.isoformat(), r, round(v, 2), stage))
        d += timedelta(days=1)
    print(f"Hujan: {got} hari berhasil, {missing} hari belum terbit/gagal ({start}..{today - timedelta(days=1)})")
    if rows:
        new = pd.DataFrame(rows, columns=["tanggal", "wilayah", "hujan_mm", "stage"])
        keep = old[~old.tanggal.isin(set(new.tanggal))]
        out = pd.concat([keep, new]).sort_values(["tanggal", "wilayah"])
        out.to_csv(p, index=False)
        print(f"rain_daily.csv: {len(out)} baris, sampai {out.tanggal.max()}")


if __name__ == "__main__":
    main()

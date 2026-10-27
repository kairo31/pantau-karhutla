"""Perbarui indeks Nino 3.4 dan DMI (NOAA PSL). Tidak fatal bila unduhan gagal:
data lama tetap dipakai. Berkas disimpan sebagai data/nino34.csv dan data/dmi.csv (date,value).
"""
import io, os, re, sys
import numpy as np, pandas as pd, requests
sys.path.insert(0, os.path.dirname(__file__))
from common import DATA

BASE = "https://psl.noaa.gov/data/timeseries/month/data/"
SOURCES = {
    "nino34": [BASE + "nino34.long.anom.csv", "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/nino34.long.anom.data"],
    "dmi": [BASE + "dmi.had.long.csv", "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data"],
}


def parse(text: str) -> pd.DataFrame:
    """Terima format CSV PSL (tanggal, nilai) maupun format .data (tahun + 12 nilai)."""
    rows = []
    for line in text.splitlines():
        parts = [p for p in re.split(r"[,\s]+", line.strip()) if p]
        if not parts:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]) and len(parts) >= 2:      # 1870-01-01, -1.0
            rows.append((pd.Timestamp(parts[0]), float(parts[1])))
        elif re.fullmatch(r"\d{4}", parts[0]) and len(parts) == 13:                  # 2024 v1 ... v12
            for m, v in enumerate(parts[1:], 1):
                rows.append((pd.Timestamp(int(parts[0]), m, 1), float(v)))
    df = pd.DataFrame(rows, columns=["date", "value"])
    df.loc[df.value <= -99, "value"] = np.nan
    return df[df.date >= "1950-01-01"].drop_duplicates("date", keep="last")


def main():
    for name, urls in SOURCES.items():
        ok = False
        for u in urls:
            try:
                r = requests.get(u, timeout=60)
                if r.status_code != 200:
                    continue
                df = parse(r.text)
                if len(df) > 500:                                                    # sanity check
                    df.assign(date=df.date.dt.strftime("%Y-%m-%d")).to_csv(DATA / f"{name}.csv", index=False)
                    last = df.dropna().date.max().date()
                    print(f"{name}: {len(df)} bulan, data valid terakhir {last}")
                    ok = True
                    break
            except requests.RequestException as e:
                print(f"{name}: {type(e).__name__} untuk {u}", file=sys.stderr)
        if not ok:
            print(f"PERINGATAN: {name} tidak berhasil diperbarui; memakai data lama.", file=sys.stderr)


if __name__ == "__main__":
    main()

"""Konstanta dan fungsi bersama untuk semua skrip pipeline."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data"

# Kotak Indonesia untuk API FIRMS: barat, selatan, timur, utara
AREA = "95,-11,141,6"
BBOX = (95.0, -11.0, 141.0, 6.0)  # minx, miny, maxx, maxy

# Kotak wilayah kasar untuk rata-rata hujan (lon_min, lon_max, lat_min, lat_max)
RAIN_REGIONS = {
    "Kalimantan": (108.5, 119.3, -4.3, 4.5),
    "Sumatera": (95.0, 106.0, -6.2, 6.0),
    "Papua": (130.5, 141.0, -10.9, 0.5),
}

REGION_ORDER = ["Nasional", "Kalimantan", "Sumatera", "Papua", "Sulawesi", "Jawa",
                "NTT", "Bali-NTB", "Maluku", "Maluku-Utara", "Lainnya"]


def assign_region(lat, lon):
    """Pembagian wilayah berbasis kotak koordinat (kasar, BUKAN batas administrasi).
    Urutan aturan penting: aturan pertama yang cocok dipakai."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    conds = [
        (lon < 106) & (lat > -6.2) & (lat < 6.1),
        (lon >= 106) & (lon <= 114.5) & (lat >= -9) & (lat <= -5.8),
        (lon >= 108.5) & (lon <= 119.3) & (lat > -4.3) & (lat <= 4.5),
        (lon >= 118.7) & (lon <= 125.5) & (lat > -6) & (lat < 2),
        (lon >= 114.5) & (lon <= 119.5) & (lat > -9.2) & (lat < -8),
        (lon >= 119.5) & (lon <= 127) & (lat < -8),
        (lon >= 127) & (lon < 130.5) & (lat > -4),
        (lon >= 130.5) & (lon <= 141.1),
        (lon >= 125.5) & (lon < 130.5) & (lat <= -2.5),
    ]
    names = ["Sumatera", "Jawa", "Kalimantan", "Sulawesi", "Bali-NTB", "NTT",
             "Maluku-Utara", "Papua", "Maluku"]
    return np.select(conds, names, default="Lainnya")


def read_daily() -> pd.DataFrame:
    p = DATA / "daily.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["acq_date", "wilayah", "titik", "frp"])


def write_daily(df: pd.DataFrame) -> None:
    df = df.sort_values(["acq_date", "wilayah"]).reset_index(drop=True)
    df["frp"] = df["frp"].round(1)
    df.to_csv(DATA / "daily.csv", index=False)


def national_series(daily: pd.DataFrame, upto=None) -> pd.Series:
    """Deret harian jumlah titik nasional, indeks harian lengkap (hari tanpa data = NaN)."""
    s = daily.groupby("acq_date").titik.sum()
    s.index = pd.to_datetime(s.index)
    end = pd.Timestamp(upto) if upto else s.index.max()
    return s.reindex(pd.date_range("2012-01-20", end))


def load_index(name: str) -> pd.Series:
    """Baca indeks bulanan (nino34/dmi) -> Series berindeks tanggal awal bulan."""
    p = DATA / f"{name}.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    x = pd.read_csv(p, parse_dates=["date"])
    return x.set_index("date").value

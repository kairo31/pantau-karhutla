"""Uji tanpa jaringan: FIRMS dan CHIRPS dipalsukan. Jalankan: pytest -q"""
import io, sys
from datetime import date, timedelta
from pathlib import Path
import numpy as np, pandas as pd, pytest, xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import common, update_firms as uf, update_rain as ur, update_enso as ue


def test_assign_region():
    r = common.assign_region([-3, -7, 0, -8.5, 1.0], [114, 107, 100, 140.0, 130])
    assert list(r) == ["Kalimantan", "Jawa", "Sumatera", "Papua", "Maluku-Utara"]


def fake_points(day: date, n=50, seed=0):
    rng = np.random.default_rng(seed + day.toordinal())
    return pd.DataFrame({"latitude": rng.uniform(-8, 2, n), "longitude": rng.uniform(100, 130, n),
                         "acq_date": day.isoformat(), "confidence": rng.choice(["n", "h", "l"], n),
                         "frp": rng.uniform(1, 30, n)})


class FakeResp:
    def __init__(self, text): self.status_code, self.text = 200, text


def fake_get_factory(calls):
    def fake_get(url, timeout=0):
        parts = url.split("/")
        key, src, area, nd, start = parts[-5], parts[-4], parts[-3], int(parts[-2]), date.fromisoformat(parts[-1])
        calls.append((src, start, nd))
        df = pd.concat([fake_points(start + timedelta(days=i)) for i in range(nd)])
        return FakeResp(df.to_csv(index=False))
    return fake_get


def test_summarize_filters_confidence():
    raw = uf.clean(fake_points(date(2026, 1, 1), 500))
    assert set(raw.confidence) <= {"n", "h"}
    s = uf.summarize(raw)
    assert s.titik.sum() == len(raw)


def test_merge_replaces_dates():
    old = pd.DataFrame({"acq_date": ["2026-01-01", "2026-01-02"], "wilayah": ["Jawa", "Jawa"], "titik": [1, 2], "frp": [1., 2.]})
    new = pd.DataFrame({"acq_date": ["2026-01-02", "2026-01-03"], "wilayah": ["Jawa", "Jawa"], "titik": [9, 3], "frp": [9., 3.]})
    m = uf.merge_daily(old, new).sort_values("acq_date")
    assert list(m.titik) == [1, 9, 3]


def test_fetch_range_chunks(monkeypatch):
    calls = []
    monkeypatch.setattr(uf.requests, "get", fake_get_factory(calls))
    df = uf.fetch_range("KEY", uf.SOURCE_NRT, date(2026, 1, 1), date(2026, 1, 23))
    assert [c[2] for c in calls] == [6, 6, 6, 5]                     # 23 hari -> 6+6+6+5
    assert df.acq_date.nunique() == 23


def test_fetch_range_chunks_7_days(monkeypatch):
    calls = []
    monkeypatch.setattr(uf.requests, "get", fake_get_factory(calls))
    uf.fetch_range("KEY", uf.SOURCE_NRT, date(2026, 1, 1), date(2026, 1, 7))
    assert [c[2] for c in calls] == [6, 1]                            # 7 hari -> 6+1


def test_fetch_rejects_ndays_above_max():
    with pytest.raises(ValueError, match="ndays harus 1-6"):
        uf.fetch("KEY", uf.SOURCE_NRT, date(2026, 1, 1), 7)


def test_main_updates_daily(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir(); (tmp_path / "out").mkdir()
    monkeypatch.setattr(common, "DATA", tmp_path / "data")
    monkeypatch.setattr(uf, "OUT", tmp_path / "out")
    monkeypatch.setenv("FIRMS_MAP_KEY", "KEY")
    calls = []
    monkeypatch.setattr(uf.requests, "get", fake_get_factory(calls))
    # data awal berhenti 5 hari lalu
    seed = uf.summarize(uf.clean(pd.concat([fake_points(date(2026, 10, 1) + timedelta(days=i)) for i in range(20)])))
    monkeypatch.setattr(uf, "read_daily", lambda: seed)
    saved = {}
    monkeypatch.setattr(uf, "write_daily", lambda df: saved.setdefault("df", df))
    monkeypatch.setattr(sys, "argv", ["x", "--today", "2026-10-26"])
    uf.main()
    out = saved["df"]
    assert out.acq_date.max() == "2026-10-25"                        # hanya sampai kemarin (hari lengkap)
    assert out.acq_date.nunique() == 25
    grid = __import__("json").loads((tmp_path / "out" / "recent_grid.json").read_text())
    assert len(grid["dates"]) == 7 and grid["asof"] == "2026-10-25" and grid["cells"]


def test_no_key(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["x"])
    with pytest.raises(SystemExit):
        uf.main()


def test_rain_region_means():
    y = np.arange(6, -11, -0.5); x = np.arange(95, 141, 0.5)
    da = xr.DataArray(np.full((len(y), len(x)), 5.0), coords={"y": y, "x": x}, dims=("y", "x"))
    da = da.where(~((da.x > 100) & (da.x < 101)))                    # sebagian kosong
    m = ur.region_means(da)
    assert set(m) == {"Kalimantan", "Sumatera", "Papua"} and all(abs(v - 5.0) < 1e-6 for v in m.values())


def test_enso_parsers():
    csv = "Date, NINO missing value -99.99 x\n2026-06-01,   1.370\n2026-07-01,-99.990\n"
    d = ue.parse("1950-01-01,0.1\n" + csv)
    assert d.value.isna().sum() == 1 and len(d) == 3
    old = "1950 2025\n2025 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0 1.1 -99.99\n-99.99\n"
    d2 = ue.parse(old)                                               # baris judul dan penutup diabaikan
    assert len(d2) == 12 and d2.value.isna().sum() == 1
    assert ue.parse("1900 " + " ".join(["0.5"] * 12)).empty           # sebelum 1950 dibuang


def test_forecast_monthly(tmp_path, monkeypatch):
    import json, forecast_monthly as fm
    rng = np.random.default_rng(1)
    days = pd.date_range("2012-08-01", "2026-10-10")
    rows = [(d, w, int(rng.poisson(20 + 400 * (d.month in (9, 10)) * (1 + (w == "Kalimantan")))), 1.0)
            for d in days for w in fm.REGIONS]
    pd.DataFrame(rows, columns=["acq_date", "wilayah", "titik", "frp"]).to_csv(tmp_path / "daily.csv", index=False)
    rd = pd.DataFrame([(d, w, 5.0, "final") for d in pd.date_range("2012-07-01", "2026-09-30") if d.month >= 7 for w in fm.REGIONS],
                      columns=["tanggal", "wilayah", "hujan_mm", "stage"])
    rd.to_csv(tmp_path / "rain_daily.csv", index=False)
    idx = pd.date_range("2012-01-01", "2026-06-01", freq="MS")
    for nm in ("nino34", "dmi"):
        pd.DataFrame({"date": idx, "value": rng.normal(0, 1, len(idx))}).to_csv(tmp_path / f"{nm}.csv", index=False)
    monkeypatch.setattr(fm, "DATA", tmp_path); monkeypatch.setattr(fm, "OUT", tmp_path / "out")
    monkeypatch.setattr(common, "DATA", tmp_path)
    monkeypatch.setattr(fm, "load_index", lambda n: common.load_index(n))
    monkeypatch.setattr(fm, "HORIZONS", [1, 2]); monkeypatch.setattr(fm, "BACKTEST_STEP", 12)
    monkeypatch.setattr(fm, "N_TREES", 20); monkeypatch.setattr(fm, "N_TREES_BT", 10)
    monkeypatch.setattr(sys, "argv", ["x", "--backtest"])
    fm.main()
    j = json.loads((tmp_path / "out" / "forecast_monthly.json").read_text())
    assert j["asof_month"] == "2026-09" and j["mtd"]["Sumatera"]["bulan"] == "2026-10" and j["mtd"]["Sumatera"]["hari"] == 10
    assert j["ffill_detail"]["nino"] == 3          # Jun -> Sep
    for m in fm.MODELS:
        for w in fm.REGIONS:
            f = j["forecast"][m][w]
            assert len(f) == 2 and all(np.isfinite(x["p"]) and x["lo"] <= x["p"] <= x["hi"] + 1 for x in f)
    assert j["backtest"]["overall"]["RF"]["skill"] < 1 and "Klimatologi" in j["backtest"]["by_h"]
    assert j["forecast"]["Ens"]["Sumatera"][0]["bulan"] == "2026-10"

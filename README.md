# Pantauan Karhutla

Situs interaktif titik panas dan kebakaran hutan/lahan Indonesia: peta terbaru, perbandingan tahun ke tahun,
prediksi akhir musim, prakiraan bulanan, hujan dan ENSO. Data diperbarui otomatis tiap hari lewat GitHub Actions.

## Pasang (sekali saja)
1. Buat repo GitHub baru, unggah seluruh isi folder ini.
2. Minta MAP_KEY gratis di https://firms.modaps.eosdis.nasa.gov/api/map_key/ lalu simpan di
   **Settings → Secrets and variables → Actions → New repository secret** dengan nama `FIRMS_MAP_KEY`.
3. **Settings → Pages → Source: GitHub Actions**.
4. **Actions → Update data dan deploy → Run workflow** (centang *backtest* untuk run pertama).
5. Domain sendiri: **Settings → Pages → Custom domain**. Di DNS, buat CNAME `www` → `<user>.github.io`
   (untuk apex pakai record A ke IP GitHub Pages). Aktifkan *Enforce HTTPS*.

## Yang berjalan tiap hari (03:30 UTC)
`update_firms.py` (NASA FIRMS, 7 hari terakhir; Minggu menyegarkan data final SP) → `update_rain.py` (CHIRPS v3) →
`update_enso.py` (Niño 3.4, DMI) → `predict.py` (prediksi akhir musim) → `forecast_monthly.py` (prakiraan bulanan) →
`build_data.py` (JSON untuk situs) → commit data → deploy. Backtest dihitung tiap Minggu atau bila dipilih manual.

Lokal: `pip install -r requirements.txt`, `pytest -q`, lalu `python -m http.server -d docs`.

## Batasan yang perlu diketahui
- Alur ke FIRMS, CHIRPS (dhis2eo), dan NOAA PSL **belum diuji langsung** dari lingkungan pengembangan; tes (`pytest`) memakai server palsu.
  Jika satu langkah gagal, langkah lain tetap jalan (hujan dan ENSO bersifat non-fatal) dan situs memakai data terakhir yang ada.
- GitHub menonaktifkan workflow terjadwal setelah 60 hari repo tanpa aktivitas; commit data harian biasanya mencegah ini.
- Data NRT beberapa hari terakhir bersifat sementara. Indeks Niño/DMI terbit dengan jeda; nilai terakhir dipakai ulang (dilaporkan di situs).
- Prediksi akhir musim: regresi logistik, dilatih dari belasan musim; 2026 berada di tepi rentang data latih.
- Prakiraan bulanan (RF + Ridge): eksperimental. Pada bulan puncak model menaksir **jauh terlalu rendah** (rasio prediksi/aktual ≈ 0,2–0,7
  pada backtest). Untuk bulan berjalan, pakai proyeksi laju harian di situs.
- Wilayah memakai kotak koordinat kasar, bukan batas administrasi. Bukan prakiraan resmi; ikuti BMKG/KLHK.

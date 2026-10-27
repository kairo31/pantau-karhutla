(() => {
"use strict";
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const MON = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"];
const CUM = [0,31,59,90,120,151,181,212,243,273,304,334];
const fmt = n => (n == null || isNaN(n)) ? "–" : Math.round(n).toLocaleString("id-ID");
const pct = n => (n == null) ? "–" : Math.round(n * 100) + "%";
const dlabel = dx => { let m = 11; while (CUM[m] > dx) m--; return `${dx - CUM[m] + 1} ${MON[m]}`; };
const dstr = s => { if (!s) return "–"; const [y, m, d] = s.split("-"); return `${+d} ${MON[+m - 1]} ${y}`; };
const isoAdd = (s, days) => new Date(Date.parse(s + "T00:00:00Z") + days * 864e5).toISOString().slice(0, 10);
const PALETTE = ["#1f6f8b","#7a5195","#2a9d8f","#b08900","#8d6e63","#43aa8b","#6d597a","#577590","#d1495b","#5b8e3a","#00798c","#9c6644","#4361ee","#bc6c25"];
const CFG = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };

let S, SEAS, PRED, RAIN, ENSO, HIST, META, GRID, MON_F;
let N, START, LASTI, ASOF_DX, ASOF_Y, YEARS = [], CUR;
let YR, DX;                      // tahun dan indeks hari (0..364, tanpa 29 Feb) per hari data
const PREP = {};
const state = { region: "Nasional", years: new Set(), map: null, layer: null };

/* ---------------- data ---------------- */
async function loadJSON(name, optional) {
  const bucket = Math.floor(Date.now() / 36e5);
  try {
    const r = await fetch(`data/${name}.json?t=${bucket}`);
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) { if (optional) return null; throw new Error(`Gagal memuat ${name}.json`); }
}

function roll(a, w, minN) {
  const out = new Array(a.length).fill(null);
  let sum = 0, cnt = 0;
  for (let i = 0; i < a.length; i++) {
    if (a[i] != null) { sum += a[i]; cnt++; }
    const j = i - w;
    if (j >= 0 && a[j] != null) { sum -= a[j]; cnt--; }
    if (cnt >= minN) out[i] = sum / cnt;
  }
  return out;
}

function buildIndex() {
  START = Date.parse(S.start + "T00:00:00Z");
  N = S.data.Nasional.n.length; LASTI = N - 1;
  YR = new Array(N); DX = new Array(N);
  for (let i = 0; i < N; i++) {
    const d = new Date(START + i * 864e5), m = d.getUTCMonth(), day = d.getUTCDate();
    YR[i] = d.getUTCFullYear();
    DX[i] = (m === 1 && day === 29) ? -1 : CUM[m] + day - 1;
  }
  CUR = YR[LASTI]; ASOF_DX = DX[LASTI] >= 0 ? DX[LASTI] : DX[LASTI - 1]; ASOF_Y = CUR;
  YEARS = []; for (let y = YR[0]; y <= CUR; y++) YEARS.push(y);
}

function prep(region) {
  if (PREP[region]) return PREP[region];
  const d = S.data[region] || S.data.Nasional;
  const sm = roll(d.n, 14, 7), fm = roll(d.f, 14, 7);
  const by = { n: {}, sm: {}, fm: {}, last: {} };
  YEARS.forEach(y => { by.n[y] = new Array(365).fill(null); by.sm[y] = new Array(365).fill(null); by.fm[y] = new Array(365).fill(null); });
  for (let i = 0; i < N; i++) {
    const x = DX[i]; if (x < 0) continue;
    by.n[YR[i]][x] = d.n[i]; by.sm[YR[i]][x] = sm[i]; by.fm[YR[i]][x] = fm[i]; by.last[YR[i]] = x;
  }
  return (PREP[region] = { n: d.n, f: d.f, sm, fm, by });
}

function metricArrays(P, metric, startDx) {
  const out = {};
  YEARS.forEach(y => {
    if (metric === "sm") out[y] = P.by.sm[y];
    else if (metric === "frp") out[y] = P.by.fm[y];
    else {
      const a = new Array(365).fill(null); let s = 0;
      const last = P.by.last[y] ?? -1;
      for (let x = startDx; x < 365 && x <= last; x++) { s += P.by.n[y][x] || 0; a[x] = s; }
      out[y] = a;
    }
  });
  return out;
}

const quant = (arr, q) => { const a = arr.filter(v => v != null).sort((x, y) => x - y); if (a.length < 3) return null;
  const i = (a.length - 1) * q, lo = Math.floor(i), hi = Math.ceil(i); return a[lo] + (a[hi] - a[lo]) * (i - lo); };
const sumRange = (a, x0, x1) => { let s = 0, any = false; for (let x = x0; x <= x1; x++) if (a[x] != null) { s += a[x]; any = true; } return any ? s : null; };

/* ---------------- tampilan umum ---------------- */
function base(extra) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: css("--ink"), family: "'Source Sans Pro', system-ui, sans-serif", size: 13 },
    margin: { l: 58, r: 14, t: 8, b: 42 },
    xaxis: { gridcolor: css("--grid"), zeroline: false, linecolor: css("--line") },
    yaxis: { gridcolor: css("--grid"), zeroline: false, linecolor: css("--line") },
    legend: { orientation: "h", y: -0.16 }, hoverlabel: { font: { family: "system-ui" } }
  }, extra || {});
}
const axX = (x0, x1) => {
  const tv = [], tt = [];
  for (let m = 0; m < 12; m++) if (CUM[m] >= x0 - 1 && CUM[m] <= x1) { tv.push(CUM[m]); tt.push(MON[m]); }
  return { tickvals: tv, ticktext: tt, range: [x0, x1], gridcolor: css("--grid"), zeroline: false, linecolor: css("--line") };
};
const labelsFor = x => x.map(dlabel);

/* ---------------- ringkasan ---------------- */
function renderKPIs() {
  const reg = state.region, P = prep(reg), prior = YEARS.filter(y => y < CUR);
  const nowSm = P.sm[LASTI];
  const medSm = quant(prior.map(y => P.by.sm[y][ASOF_DX]), .5);
  const ratio = (medSm && medSm > 0) ? nowSm / medSm : null;
  const w7 = sumRange(P.by.n[CUR], ASOF_DX - 6, ASOF_DX);
  const p7 = prior.map(y => sumRange(P.by.n[y], ASOF_DX - 6, ASOF_DX)).filter(v => v != null);
  const p7m = quant(p7, .5);
  const sx = ASOF_DX >= 181 ? 181 : 0;
  const tot = YEARS.map(y => ({ y, v: sumRange(P.by.n[y], sx, ASOF_DX) }));
  const cur = tot.find(t => t.y === CUR).v;
  const rank = tot.filter(t => t.v != null && t.v > cur).length + 1;
  const season = (SEAS[reg] || []).find(s => s.y === CUR);
  const cards = [
    [fmt(nowSm), "Rata-rata 14 hari", ratio != null ? `${ratio.toFixed(1).replace(".", ",")}× median tahun lalu` : "", ratio > 1 ? "up" : "dn"],
    [fmt(w7), "Total 7 hari", p7m ? `Median tahun lalu: ${fmt(p7m)}` : "", ""],
    [`Ke-${rank} dari ${tot.filter(t => t.v != null).length}`, "Peringkat tahunan", `Total ${sx ? "Jul" : "Jan"}–${dlabel(ASOF_DX)}: ${fmt(cur)} titik`, ""],
    [season ? fmt(season.peakv) : "–", "Puncak tahun ini", season ? dstr(season.peak) : "", ""],
  ];
  if (PRED && PRED.status === "ok" && PRED.thresholds["1000"] && PRED.thresholds["1000"].models.B && reg === "Nasional") {
    const md = PRED.thresholds["1000"].models.B.median_date;
    cards.push([md ? dstr(md) : "> 70 hari", "Median turun <1.000/hari", "Perkiraan nasional", ""]);
  }
  $("kpis").innerHTML = cards.map(c => `<div class="kpi"><div class="l">${c[1]}</div><div class="v">${c[0]}</div><div class="d ${c[3]}">${c[2]}</div></div>`).join("");
}

function renderOverview() {
  const P = prep(state.region), prior = YEARS.filter(y => y < CUR), x0 = 181, x1 = 364;
  const x = Array.from({ length: x1 - x0 + 1 }, (_, i) => x0 + i), lb = labelsFor(x);
  const q = p => x.map(d => quant(prior.map(y => P.by.sm[y][d]), p));
  const lo = q(.1), hi = q(.9), md = q(.5);
  const tr = [
    { x, y: lo, mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false },
    { x, y: hi, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: css("--band"), name: "rentang 10–90% (2012–" + (CUR - 1) + ")", hoverinfo: "skip" },
    { x, y: md, mode: "lines", line: { color: css("--past"), width: 1.6, dash: "dot" }, name: "median", customdata: lb, hovertemplate: "median %{customdata}: %{y:,.0f}<extra></extra>" },
    { x, y: x.map(d => P.by.sm[CUR][d]), mode: "lines", name: String(CUR), line: { color: css("--accent"), width: 3.2 }, customdata: lb, hovertemplate: `<b>${CUR}</b> %{customdata}<br>%{y:,.0f} titik/hari<extra></extra>`, connectgaps: false },
  ];
  Plotly.react("p-overview", tr, base({ xaxis: axX(x0, x1),   yaxis: { title: { text: "Titik panas per hari" }, gridcolor: css("--grid"), zeroline: false, rangemode: "tozero" } }), CFG);
}

/* ---------------- peta ---------------- */
const BOX = { Nasional: [[-11, 95], [6, 141]], Kalimantan: [[-4.3, 108.5], [4.5, 119.3]], Sumatera: [[-6.2, 95], [6, 106]],
  Papua: [[-10.9, 130.5], [0.5, 141]], Sulawesi: [[-6, 118.7], [2, 125.5]], Jawa: [[-9, 106], [-5.8, 114.5]], NTT: [[-11, 119.5], [-8, 127]],
  "Bali-NTB": [[-9.2, 114.5], [-8, 119.5]], Maluku: [[-8, 125.5], [-2.5, 130.5]], "Maluku-Utara": [[-4, 127], [3, 130.5]], Lainnya: [[-11, 95], [6, 141]] };
const MCOL = ["#fde68a", "#fb923c", "#ef4444", "#991b1b", "#450a0a"];
const MTH = { n: [1, 3, 10, 30], f: [10, 50, 200, 600] };

function initMap() {
  if (typeof L === "undefined") { $("map").innerHTML = '<p class="msg">Pustaka peta (Leaflet) tidak termuat.</p>'; return; }
  state.map = L.map("map", { preferCanvas: true, zoomControl: true, minZoom: 4 });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 12, attribution: "© OpenStreetMap" }).addTo(state.map);
  state.layer = L.layerGroup().addTo(state.map);
  state.map.fitBounds(BOX.Nasional);
  $("map-days").addEventListener("change", renderMap); $("map-metric").addEventListener("change", renderMap);
}

function renderMap() {
  if (!state.map) return;
  if (!GRID) { $("map-info").textContent = "Data peta belum tersedia."; return; }
  const k = +$("map-days").value, met = $("map-metric").value, nD = GRID.dates.length, from = nD - k;
  state.layer.clearLayers();
  const rows = [];
  for (const c of GRID.cells) {
    const arr = met === "n" ? c[2] : c[3]; let v = 0;
    for (let i = from; i < nD; i++) v += arr[i];
    if (v > 0) rows.push([c, v]);
  }
  rows.sort((a, b) => a[1] - b[1]);
  const th = MTH[met];
  rows.forEach(([c, v]) => {
    const ci = th.filter(t => v >= t).length - 1 < 0 ? 0 : th.filter(t => v >= t).length;
    const col = MCOL[Math.min(ci, MCOL.length - 1)];
    const m = L.circleMarker([c[0], c[1]], { radius: Math.min(3 + 1.6 * Math.sqrt(v / (met === "f" ? 8 : 1)), 15), color: col, weight: 0.6, fillColor: col, fillOpacity: .62 });
    const days = GRID.dates.slice(from).map((d, i) => `<tr><td>${dstr(d)}</td><td style="text-align:right">${c[2][from + i]}</td><td style="text-align:right">${c[3][from + i]}</td></tr>`).join("");
    m.bindPopup(`<b>${c[0].toFixed(2)}, ${c[1].toFixed(2)}</b><br>${fmt(v)} ${met === "n" ? "titik" : "MW"} dalam ${k} hari<table style="font-size:.8rem;margin-top:4px"><tr><th>Tanggal</th><th>Titik</th><th>MW</th></tr>${days}</table>`);
    state.layer.addLayer(m);
  });
  $("map-info").textContent = `${fmt(rows.length)} sel aktif · ${dstr(GRID.dates[from])}${k > 1 ? " – " + dstr(GRID.dates[nD - 1]) : ""}`;
  const regionTotals = {};
  const regionForPoint = (lat, lon) => {
    const rules = [
      ["Sumatera", lon < 106 && lat > -6.2 && lat < 6.1],
      ["Jawa", lon >= 106 && lon <= 114.5 && lat >= -9 && lat <= -5.8],
      ["Kalimantan", lon >= 108.5 && lon <= 119.3 && lat > -4.3 && lat <= 4.5],
      ["Sulawesi", lon >= 118.7 && lon <= 125.5 && lat > -6 && lat < 2],
      ["Bali-NTB", lon >= 114.5 && lon <= 119.5 && lat > -9.2 && lat < -8],
      ["NTT", lon >= 119.5 && lon <= 127 && lat < -8],
      ["Maluku-Utara", lon >= 127 && lon < 130.5 && lat > -4],
      ["Papua", lon >= 130.5 && lon <= 141.1],
      ["Maluku", lon >= 125.5 && lon < 130.5 && lat <= -2.5]
    ];
    return (rules.find(r => r[1]) || ["Lainnya"])[0];
  };
  rows.forEach(([c, v]) => {
    const region = regionForPoint(c[0], c[1]);
    regionTotals[region] = (regionTotals[region] || 0) + v;
  });
  const ranked = Object.entries(regionTotals).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const total = Object.values(regionTotals).reduce((sum, value) => sum + value, 0);
  $("rank-period").textContent = `${dstr(GRID.dates[from])}${k > 1 ? " – " + dstr(GRID.dates[nD - 1]) : ""}`;
  $("map-ranking").innerHTML = ranked.length ? ranked.map(([name, value]) => {
    const share = total ? Math.round(value / total * 100) : 0;
    return `<div class="ranking-row"><span class="ranking-name">${name}</span><span class="ranking-track"><i style="width:${share}%"></i><b>${share}%</b></span><span class="ranking-value">${fmt(value)} ${met === "n" ? "titik" : "MW"}</span></div>`;
  }).join("") : '<p class="note">Belum ada data peta.</p>';
  const unit = met === "n" ? "titik" : "MW";
  const labels = [
    `<span><i style="background:${MCOL[0]}"></i>Rendah: &lt; ${th[0]} ${unit}</span>`,
    `<span><i style="background:${MCOL[1]}"></i>Sedang: ${th[0]}–${th[1] - 1} ${unit}</span>`,
    `<span><i style="background:${MCOL[2]}"></i>Tinggi: ${th[1]}–${th[2] - 1} ${unit}</span>`,
    `<span><i style="background:${MCOL[3]}"></i>Sangat tinggi: ${th[2]}–${th[3] - 1} ${unit}</span>`,
    `<span><i style="background:${MCOL[4]}"></i>Ekstrem: ≥ ${th[3]} ${unit}</span>`
  ];
  $("map-legend").innerHTML = `<strong>Keterangan intensitas ${met === "n" ? "titik panas" : "FRP"}</strong>${labels.join("")}`;
}

/* ---------------- bandingkan tahun ---------------- */
function yearColor(y, i) { return y === CUR ? css("--accent") : PALETTE[i % PALETTE.length]; }

function renderChips() {
  $("chips").innerHTML = "";
  YEARS.forEach((y, i) => {
    const label = document.createElement("label");
    label.className = "year-check";
    const input = document.createElement("input");
    input.type = "checkbox"; input.value = y; input.checked = state.years.has(y);
    input.style.accentColor = yearColor(y, i);
    input.addEventListener("change", () => {
      input.checked ? state.years.add(y) : state.years.delete(y);
      renderCompare();
    });
    const text = document.createElement("span");
    text.textContent = y;
    label.append(input, text);
    $("chips").appendChild(label);
  });
}

function setPreset(p) {
  const P = prep(state.region), prior = YEARS.filter(y => y < CUR);
  const tot = prior.map(y => ({ y, v: sumRange(P.by.n[y], 181, 364) || 0 })).sort((a, b) => b.v - a.v);
  if (p === "worst") state.years = new Set([CUR, ...tot.slice(0, 3).map(t => t.y)]);
  if (p === "last5") state.years = new Set(YEARS.slice(-5));
  if (p === "all") state.years = new Set(YEARS);
  if (p === "none") state.years = new Set([CUR]);
  renderChips(); renderCompare();
}

function renderCompare() {
  const P = prep(state.region), metric = $("cmp-metric").value, range = $("cmp-range").value;
  const x0 = range === "jul" ? 181 : 0, x1 = 364, startDx = x0;
  const M = metricArrays(P, metric, startDx), prior = YEARS.filter(y => y < CUR);
  const x = Array.from({ length: x1 - x0 + 1 }, (_, i) => x0 + i), lb = labelsFor(x);
  const unit = metric === "cum" ? "titik" : metric === "frp" ? "MW/hari" : "titik/hari";
  const tr = [];
  if ($("cmp-band").checked) {
    const q = p => x.map(d => quant(prior.map(y => M[y][d]), p));
    tr.push({ x, y: q(.1), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false });
    tr.push({ x, y: q(.9), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: css("--band"), name: "Rentang 10–90% semua tahun lalu", hoverinfo: "skip" });
  }
  YEARS.forEach((y, i) => {
    if (!state.years.has(y)) return;
    tr.push({ x, y: x.map(d => M[y][d]), mode: "lines", name: String(y), customdata: lb, connectgaps: false,
      line: { color: yearColor(y, i), width: y === CUR ? 3.4 : 1.8 },
      hovertemplate: `<b>${y}</b> %{customdata}<br>%{y:,.0f} ${unit}<extra></extra>` });
  });
  Plotly.react("p-cmp", tr, base({ xaxis: axX(x0, x1),
    yaxis: { title: { text: metric === "cum" ? "Titik panas (kumulatif)" : unit }, gridcolor: css("--grid"), zeroline: false, rangemode: "tozero" },
    hovermode: "closest" }), CFG);

  // batang: total sampai tanggal yang sama
  const sx = ASOF_DX >= 181 ? 181 : 0;
  $("bar-sub").textContent = "";
  const vals = YEARS.map(y => sumRange(P.by.n[y], sx, ASOF_DX));
  Plotly.react("p-bar", [{ type: "bar", x: YEARS.map(String), y: vals, marker: { color: YEARS.map(y => y === CUR ? css("--accent") : css("--blue")) },
    hovertemplate: "<b>%{x}</b><br>%{y:,.0f} titik<extra></extra>" }],
    base({ xaxis: { type: "category", gridcolor: "rgba(0,0,0,0)" }, yaxis: { gridcolor: css("--grid"), zeroline: false, title: { text: "Titik panas" } }, showlegend: false }), CFG);

  // tabel musim
  const rows = (SEAS[state.region] || []).slice().reverse().map(t =>
    `<tr class="${t.ongoing ? "cur" : ""}"><td>${t.y}${t.ongoing ? " (berjalan)" : ""}</td><td>${dstr(t.peak)}</td><td class="n">${fmt(t.peakv)}</td><td class="n">${fmt(t.total)}</td><td>${t.ongoing && !t.end ? "belum" : dstr(t.end)}</td></tr>`).join("");
  $("tbl").innerHTML = `<thead><tr><th>Musim</th><th>Puncak</th><th class="n">Titik/hari</th><th class="n">Jul–Des</th><th>Akhir</th></tr></thead><tbody>${rows}</tbody>`;
}

/* ---------------- prediksi ---------------- */
function crossDate(asof, hs, ps, q) {
  const xs = [0, ...hs], ys = [0, ...ps];
  for (let i = 1; i < xs.length; i++) if (ys[i] >= q) {
    const f = (q - ys[i - 1]) / Math.max(ys[i] - ys[i - 1], 1e-9);
    return isoAdd(asof, Math.round(xs[i - 1] + f * (xs[i] - xs[i - 1])));
  }
  return null;
}

function initPrediction() {
  const th = $("pr-th"), md = $("pr-model");
  Object.keys(PRED.thresholds).forEach(k => { const o = document.createElement("option"); o.value = k;
    o.textContent = `Turun di bawah ${(+k).toLocaleString("id-ID")} titik/hari`; th.appendChild(o); });
  Object.entries(PRED.labels).forEach(([k, v]) => { const o = document.createElement("option"); o.value = k; o.textContent = v; md.appendChild(o); });
  md.value = "B";
  [th, md, $("pr-all")].forEach(e => e.addEventListener("change", renderPrediction));
}

function renderPrediction() {
  const th = $("pr-th").value, model = $("pr-model").value, T = PRED.thresholds[th], msg = $("pred-msg");
  msg.hidden = true;
  let M = T && T.models[model];
  if (PRED.status !== "ok") { msg.hidden = false; msg.textContent = PRED.note || "Model belum berlaku untuk tanggal ini."; }
  else if (T.already_below) { msg.hidden = false; msg.textContent = "Rata-rata 14 hari sudah di bawah ambang ini. Pilih ambang yang lebih rendah."; }
  else if (!M) { msg.hidden = false; msg.textContent = "Model ini belum tersedia (data fitur belum lengkap, misalnya hujan atau Niño)."; }
  const hs = PRED.horizons;
  if (M) {
    const dates = [PRED.asof, ...hs.map(h => isoAdd(PRED.asof, h))];
    const lab = d => dstr(d);
    const mk = (m, name, dash, w) => ({ x: dates, y: [0, ...m.p], name, mode: "lines+markers", line: { width: w, dash }, marker: { size: 5 },
      customdata: dates.map(lab), hovertemplate: `${name}<br>%{customdata}: %{y:.0%}<extra></extra>` });
    const tr = [];
    const showAll = $("pr-all").checked;
    if (!showAll) {
      tr.push({ x: dates, y: [0, ...M.p10.map(v => v ?? 0)], mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false });
      tr.push({ x: dates, y: [0, ...M.p90.map(v => v ?? 0)], mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: css("--band"), name: "Rentang 10–90%", hoverinfo: "skip" });
    }
    const colors = { A: css("--past"), B: css("--accent"), C: css("--blue") };
    (showAll ? Object.keys(T.models) : [model]).forEach(k => { const t = mk(T.models[k], PRED.labels[k], k === "A" ? "dot" : "solid", k === model ? 3.2 : 2); t.line.color = colors[k]; t.marker.color = colors[k]; tr.push(t); });
    const med = M.median_date;
    const shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: .5, y1: .5, line: { color: css("--muted"), width: 1, dash: "dot" } }];
    if (med) shapes.push({ type: "line", x0: med, x1: med, y0: 0, y1: 1, line: { color: colors[model], width: 1.2, dash: "dash" } });
    Plotly.react("p-pred", tr, base({ xaxis: { type: "date", gridcolor: css("--grid"), zeroline: false, tickformat: "%-d %b" },
      yaxis: { title: { text: "Peluang sudah turun di bawah ambang" }, tickformat: ".0%", range: [0, 1.02], gridcolor: css("--grid"), zeroline: false },
      shapes, hovermode: "closest" }), CFG);
    const d10 = crossDate(PRED.asof, hs, M.p, .1), d90 = crossDate(PRED.asof, hs, M.p, .9);
    $("pred-kpis").innerHTML = [
      [med ? dstr(med) : `> ${dstr(isoAdd(PRED.asof, hs[hs.length - 1]))}`, "Tanggal median (peluang 50%)"],
      [d10 ? dstr(d10) : "–", "Peluang 10% (awal)"], [d90 ? dstr(d90) : `> ${dstr(isoAdd(PRED.asof, hs[hs.length - 1]))}`, "Peluang 90% (akhir)"],
      [pct(M.p[3]), `Peluang sudah turun pada ${dstr(isoAdd(PRED.asof, hs[3]))}`]
    ].map(c => `<div class="kpi"><div class="v">${c[0]}</div><div class="l">${c[1]}</div></div>`).join("");
  } else { Plotly.purge("p-pred"); $("p-pred").innerHTML = ""; $("pred-kpis").innerHTML = ""; }

  // analog
  const A = (PRED.analogs || {})[th] || [];
  const rowsA = A.slice().sort((a, b) => b.level - a.level).map(a => {
    const done = a.days_left != null && a.days_left <= 0;
    return `<tr><td>${a.year}</td><td class="n">${fmt(a.level)}</td><td class="n">${a.days_left == null ? "Tidak turun" : done ? "Sudah turun" : a.days_left + " hari"}</td><td>${dstr(a.end)}</td></tr>`;
  }).join("");
  $("tbl-ana").innerHTML = `<thead><tr><th>Tahun</th><th class="n">Level</th><th class="n">Sisa</th><th>Turun pada</th></tr></thead><tbody>${rowsA}</tbody>`;

  // riwayat
  const H = (HIST || []).filter(h => String(h.ambang) === th && h.model === model && h.median_date);
  if (H.length >= 2) {
    Plotly.react("p-hist", [{ x: H.map(h => h.asof), y: H.map(h => h.median_date), mode: "lines+markers", line: { color: css("--accent"), width: 2.4 }, marker: { size: 5 },
      hovertemplate: "Per %{x}: median %{y|%-d %b %Y}<extra></extra>" }],
      base({ xaxis: { type: "date", gridcolor: css("--grid") }, yaxis: { type: "date", gridcolor: css("--grid"), title: { text: "Tanggal median" }, tickformat: "%-d %b" }, showlegend: false }), CFG);
  } else {
    Plotly.purge("p-hist");
    $("p-hist").innerHTML = `<div class="empty-history">
      <img src="assets/prediction-history-empty.png" alt="Ilustrasi data histori belum tersedia">
    </div>`;
  }
}

/* ---------------- hujan dan ENSO ---------------- */
function renderRain() {
  let reg = state.region;
  if (!RAIN || !RAIN.regions[reg]) reg = "Kalimantan";
  const R = RAIN.regions[reg];
  const years = Object.keys(R).map(Number);
  // kumulatif sejak 1 Sep (indeks 62 pada array Jul–Des)
  const tr = [], xs = Array.from({ length: 122 }, (_, i) => i), lbl = xs.map(i => dlabel(243 + i));
  years.forEach(y => {
    const a = R[y].slice(62); let s = 0, ok = true; const c = a.map(v => { if (v == null) ok = false; if (!ok) return null; s += v; return s; });
    tr.push({ x: xs, y: c, mode: "lines", name: String(y), showlegend: y === CUR, customdata: lbl, connectgaps: false,
      line: { color: y === CUR ? css("--accent") : css("--past"), width: y === CUR ? 3.2 : 1 }, opacity: y === CUR ? 1 : .6,
      hovertemplate: `<b>${y}</b> %{customdata}<br>%{y:,.0f} mm<extra></extra>` });
  });
  Plotly.react("p-rcum", tr, base({ xaxis: { tickvals: [0, 30, 61, 91], ticktext: ["1 Sep", "1 Okt", "1 Nov", "1 Des"], gridcolor: css("--grid"), zeroline: false },
    yaxis: { title: { text: "Mm sejak 1 Sep" }, gridcolor: css("--grid"), zeroline: false, rangemode: "tozero" }, hovermode: "closest", showlegend: false }), CFG);

  // sebar hujan Agu–Sep vs titik panas
  const P = prep(reg), sx = 212, pts = [];
  years.forEach(y => {
    const a = R[y].slice(31, 92).filter(v => v != null);
    const f = sumRange(P.by.n[y], sx, ASOF_DX);
    if (a.length >= 55 && f != null && f > 0) pts.push({ y, r: a.reduce((s, v) => s + v, 0) / a.length, f });
  });
  const hist = pts.filter(p => p.y < CUR), cur = pts.find(p => p.y === CUR);
  let corr = null, sl = 0, ic = 0;
  if (hist.length > 3) {
    const xr = hist.map(p => p.r), yl = hist.map(p => Math.log(p.f)), mx = xr.reduce((a, b) => a + b) / xr.length, my = yl.reduce((a, b) => a + b) / yl.length;
    let sxy = 0, sxx = 0, syy = 0; xr.forEach((v, i) => { sxy += (v - mx) * (yl[i] - my); sxx += (v - mx) ** 2; syy += (yl[i] - my) ** 2; });
    sl = sxy / sxx; ic = my - sl * mx; corr = sxy / Math.sqrt(sxx * syy);
  }
  const trs = [];
  if (corr != null) { const lx = [Math.min(...pts.map(p => p.r)) - .3, Math.max(...pts.map(p => p.r)) + .3]; trs.push({ x: lx, y: lx.map(v => Math.exp(ic + sl * v)), mode: "lines", line: { color: css("--muted"), width: 1.4, dash: "dot" }, hoverinfo: "skip", showlegend: false }); }
  trs.push({ x: hist.map(p => p.r), y: hist.map(p => p.f), text: hist.map(p => p.y), mode: "markers+text", textposition: "top center", textfont: { size: 10, color: css("--muted") },
    marker: { color: css("--blue"), size: 9 }, showlegend: false, hovertemplate: "<b>%{text}</b><br>hujan %{x:.1f} mm/hari<br>%{y:,.0f} titik<extra></extra>" });
  if (cur) trs.push({ x: [cur.r], y: [cur.f], text: [CUR], mode: "markers+text", textposition: "top center", textfont: { size: 12, color: css("--accent") }, marker: { color: css("--accent"), size: 13 }, showlegend: false,
    hovertemplate: "<b>%{text}</b><br>hujan %{x:.1f} mm/hari<br>%{y:,.0f} titik<extra></extra>" });
  const fs = pts.map(p => p.f), lo = Math.min(...fs) * .6, hi = Math.max(...fs) * 1.8;
  const tv = [1e3, 3e3, 1e4, 3e4, 1e5, 3e5, 1e6].filter(v => v >= lo && v <= hi);
  Plotly.react("p-rsc", trs, base({ xaxis: { title: { text: "Hujan Agu–Sep (mm/hari)" }, gridcolor: css("--grid"), zeroline: false },
    yaxis: { type: "log", title: { text: "Titik panas" }, range: [Math.log10(lo), Math.log10(hi)], tickvals: tv, ticktext: tv.map(v => v >= 1e6 ? "1 jt" : (v / 1000) + " rb"), gridcolor: css("--grid"), zeroline: false } }), CFG);

  // ENSO
  if (ENSO) {
    const [sy, sm] = ENSO.start.split("-").map(Number);
    const xm = ENSO.nino.map((_, i) => { const t = (sm - 1) + i; return `${sy + Math.floor(t / 12)}-${String(t % 12 + 1).padStart(2, "0")}-01`; });
    Plotly.react("p-enso", [
      { x: xm, y: ENSO.nino, name: "Niño 3.4", mode: "lines", line: { color: css("--nino"), width: 2.2 }, connectgaps: false, hovertemplate: "%{x|%b %Y}: %{y:.2f} °C<extra>Niño 3.4</extra>" },
      { x: xm, y: ENSO.dmi, name: "DMI (IOD)", mode: "lines", line: { color: css("--dmi"), width: 2 }, connectgaps: false, hovertemplate: "%{x|%b %Y}: %{y:.2f} °C<extra>DMI</extra>" }],
      base({ xaxis: { type: "date", gridcolor: css("--grid"), range: [xm[0], `${CUR}-12-31`] }, yaxis: { title: { text: "Anomali (°C)" }, gridcolor: css("--grid"), zerolinecolor: css("--muted") },
        shapes: [{ type: "rect", xref: "paper", x0: 0, x1: 1, y0: -.5, y1: .5, fillcolor: css("--band"), line: { width: 0 }, layer: "below" }] }), CFG);
  }
}


/* ---------------- prakiraan bulanan ---------------- */
const mlab = m => { const [y, mm] = m.split("-"); return `${MON[+mm - 1]} ${y}`; };
function initMonthly() {
  if (!MON_F) { $("bulanan").hidden = true; document.querySelector('nav a[href="#bulanan"]').hidden = true; return; }
  MON_F.regions.forEach(r => { const o = document.createElement("option"); o.value = r; o.textContent = r; $("mo-reg").appendChild(o); });
  $("mo-reg").value = MON_F.regions.includes(state.region) ? state.region : "Kalimantan";
  ["mo-reg", "mo-both"].forEach(id => $(id).addEventListener("change", renderMonthly));
}
function renderMonthly() {
  if (!MON_F) return;
  const w = $("mo-reg").value, F = MON_F, hist = F.history[w], mt = F.mtd && F.mtd[w];
  $("mo-lead").textContent = "";
  const col = { RF: css("--accent"), Ridge: css("--blue"), Ens: css("--green") || css("--muted") }, tr = [];
  const hx = hist.bulan.map(m => m + "-01");
  tr.push({ x: hx, y: hist.titik, name: "aktual", mode: "lines", line: { color: css("--ink"), width: 1.8 }, hovertemplate: "%{x|%b %Y}: %{y:,.0f}<extra>aktual</extra>" });
  const models = $("mo-both").checked ? ["RF", "Ridge", "Ens"] : ["Ens"];
  models.forEach(m => {
    const f = F.forecast[m][w], x = f.map(d => d.bulan + "-01");
    if (m === "Ens") {
      tr.push({ x, y: f.map(d => d.lo), mode: "lines", line: { width: 0 }, hoverinfo: "skip", showlegend: false });
      tr.push({ x, y: f.map(d => d.hi), mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: css("--band"), name: "rentang 80% (rata-rata)", hoverinfo: "skip" });
    }
    tr.push({ x: [hx[hx.length - 1], ...x], y: [hist.titik[hist.titik.length - 1], ...f.map(d => d.p)], name: F.labels[m], mode: "lines+markers",
      line: { color: col[m], width: 2.6, dash: m === "Ridge" ? "dash" : m === "RF" ? "dot" : "solid" }, marker: { size: 6 }, hovertemplate: `%{x|%b %Y}: %{y:,.0f}<extra>${F.labels[m]}</extra>` });
  });
  if (mt) {
    const x = mt.bulan + "-01";
    tr.push({ x: [x], y: [mt.sejauh_ini], name: "Aktual sejauh ini", mode: "markers", marker: { symbol: "diamond", size: 11, color: css("--ink") }, hovertemplate: `${mt.hari} hari: %{y:,.0f}<extra>Sejauh ini</extra>` });
    tr.push({ x: [x], y: [mt.proyeksi_laju], name: "Proyeksi laju harian", mode: "markers", marker: { symbol: "x", size: 12, color: css("--accent"), line: { width: 2 } }, hovertemplate: "%{y:,.0f}<extra>Jika laju harian bertahan</extra>" });
  }
  Plotly.react("p-mo", tr, base({ xaxis: { type: "date", gridcolor: css("--grid"), range: [hx[hx.length - 36], F.forecast.Ens[w][5].bulan + "-28"] },
    yaxis: { type: "log", title: { text: "Titik panas per bulan" }, gridcolor: css("--grid"), zeroline: false }, hovermode: "closest" }), CFG);
  const f1 = F.forecast.Ens[w][0], r1 = F.forecast.RF[w][0];
  $("mo-kpis").innerHTML = (mt ? [
    [fmt(mt.sejauh_ini), `${mlab(mt.bulan)}: aktual ${mt.hari} hari pertama`],
    [fmt(mt.proyeksi_laju), "Proyeksi bila laju harian bertahan"],
    [`${fmt(f1.p)} / ${fmt(r1.p)}`, `Rata-rata model/RF untuk ${mlab(f1.bulan)}`]] :
    [[fmt(f1.p), `Rata-rata model ${mlab(f1.bulan)}`], [fmt(r1.p), `RF ${mlab(f1.bulan)}`]]).map(c => `<div class="kpi"><div class="v">${c[0]}</div><div class="l">${c[1]}</div></div>`).join("");
  $("mo-note").innerHTML = (mt && f1.p < mt.sejauh_ini ? `<b>Peringatan:</b> prakiraan model ${mlab(f1.bulan)} (${fmt(f1.p)}) sudah lebih kecil dari aktual sejauh ini (${fmt(mt.sejauh_ini)}). Untuk bulan yang sedang berjalan, andalkan proyeksi laju harian. ` : "") +
    (F.ffill_bulan_indeks > 0 ? `Indeks Niño/DMI belum terbit untuk ${F.ffill_bulan_indeks} bulan terakhir; nilai terakhir yang ada dipakai. ` : "") +
    "Model cenderung menaksir terlalu rendah pada bulan puncak, terutama di tahun ekstrem.";

}

/* ---------------- kendali ---------------- */
function renderAll() {
  renderKPIs(); renderOverview(); renderMap(); renderChips(); renderCompare(); renderPrediction(); renderMonthly(); renderRain();
}

function setupControls() {
  const sel = $("reg");
  S.regions.forEach(r => { const o = document.createElement("option"); o.value = r; o.textContent = r; sel.appendChild(o); });
  sel.addEventListener("change", () => {
    state.region = sel.value; setPreset(state.years.size > 1 ? "worst" : "none");
    renderKPIs(); renderOverview(); renderRain();
    if (state.map && BOX[state.region]) state.map.fitBounds(BOX[state.region]);
  });
  $("theme").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
    try { localStorage.setItem("theme", dark ? "light" : "dark"); } catch (e) {}
    renderAll();
  });
  ["cmp-metric", "cmp-range", "cmp-band"].forEach(id => $(id).addEventListener("change", renderCompare));
  document.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () => setPreset(b.dataset.preset)));
}

async function main() {
  try { const t = localStorage.getItem("theme"); if (t) document.documentElement.setAttribute("data-theme", t); } catch (e) {}
  try {
    [S, SEAS, PRED, RAIN, ENSO, HIST, META, GRID, MON_F] = await Promise.all([
      loadJSON("series"), loadJSON("seasons"), loadJSON("prediction"), loadJSON("rain", true), loadJSON("enso", true),
      loadJSON("prediction_history", true), loadJSON("meta", true), loadJSON("recent_grid", true), loadJSON("forecast_monthly", true)]);
  } catch (e) { $("status").textContent = e.message + ". Muat ulang halaman."; return; }
  buildIndex();
  $("status").textContent = `Titik panas sampai ${dstr(S.last)}` + (RAIN ? ` · hujan sampai ${dstr(RAIN.last)}` : "") +
    (ENSO && ENSO.nino_last ? ` · Niño 3.4 sampai ${ENSO.nino_last}` : "") + (META ? ` · diperbarui ${META.generated}` : "");
  setupControls(); initMap(); initPrediction(); initMonthly();
  state.years = new Set([CUR]); setPreset("worst");
  renderAll();
  addEventListener("resize", () => { if (state.map) state.map.invalidateSize(); });
}
main();
})();

import { addMlOutlookLayer, cellSummary, MODES, LOW_SKILL, skillWord } from './ml-outlook-layer.mjs';

const $ = s => document.querySelector(s);
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthName = ym => { const [y, m] = ym.split('-'); return [MON[+m - 1], y]; };
const cellName = c => `${-c.lat - 0.5}–${-c.lat + 0.5}°S · ${c.lon - 0.5}–${c.lon + 0.5}°E`;

const [data, outline] = await Promise.all([
  fetch('../outputs/ml_outlook_layer.json').then(r => r.json()),
  fetch('../outputs/wa_outline.geojson').then(r => r.json()),
]);

const q = new URLSearchParams(location.search);
const state = {
  issue: data.issues.some(i => i.key === q.get('issue')) ? q.get('issue') : data.issues.at(-1).key,
  mode: MODES[q.get('mode')] ? q.get('mode') : 'anom',
  month: Math.min(5, Math.max(0, +q.get('month') || 0)),
  view: q.get('view') === 'table' ? 'table' : 'map',
  cell: q.get('cell') || data.localities.find(l => l.name === 'Fitzroy Crossing').cell,
};
const issueObj = () => data.issues.find(i => i.key === state.issue);
const syncUrl = () => history.replaceState(null, '', '?' + new URLSearchParams(state));

const map = new maplibregl.Map({
  container: 'map',
  style: {
    version: 8,
    sources: { wa: { type: 'geojson', data: outline, attribution: 'Outline: Natural Earth' } },
    layers: [
      { id: 'sea', type: 'background', paint: { 'background-color': '#dfe7ea' } },
      { id: 'wa-land', type: 'fill', source: 'wa', paint: { 'fill-color': '#f3f1ea' } },
      { id: 'wa-outline', type: 'line', source: 'wa', paint: { 'line-color': '#4b4f4b', 'line-width': 1 } },
    ],
  },
  bounds: [[111.5, -36.2], [129.6, -13.2]],
  fitBoundsOptions: { padding: { top: 60, bottom: 90, left: 20, right: 20 } },
  attributionControl: { compact: false },
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
window.__map = map;

await new Promise(r => map.on('load', r));

const ml = addMlOutlookLayer(map, data, {
  issue: state.issue, month: state.month, mode: state.mode, beforeId: 'wa-outline',
  onSelect: s => { state.cell = s?.id ?? state.cell; renderPanel(s); renderTable(); syncUrl(); },
  onHover: h => {
    const tip = $('#tooltip');
    if (!h) { tip.hidden = true; return; }
    const m = h.cell.months[h.month];
    tip.innerHTML = `<b>${h.cell.locality ?? cellName(h.cell)}</b> · ${MODES.temp.fmt(m.temp)} · ${MODES.anom.fmt(m.anom)} · ${MODES.prob.fmt(m.prob)} warmer`;
    tip.style.left = `${h.point.x + 14}px`; tip.style.top = `${h.point.y + 14}px`; tip.hidden = false;
  },
});
window.__ml = ml;

for (const l of data.localities) {
  const el = document.createElement('div');
  el.className = 'loc';
  el.innerHTML = `<i></i>${l.name}`;
  new maplibregl.Marker({ element: el, anchor: 'left', offset: [-4, 0] }).setLngLat([l.lon, l.lat]).addTo(map);
}

// ---------------------------------------------------------------- controls

$('#issue').innerHTML = data.issues.map(i => `<option value="${i.key}">${i.label} issue${i.uses_partial_month ? ' (uses partial month)' : ''}</option>`).join('');
$('#issue').value = state.issue;
$('#issue').onchange = e => { state.issue = e.target.value; ml.setIssue(state.issue); renderAll(); };

$('#modes').innerHTML = Object.entries({ anom: 'Difference', prob: 'Chance warmer', temp: 'Temperature' })
  .map(([k, v]) => `<button role="radio" data-mode="${k}">${v}</button>`).join('');
$('#modes').onclick = e => { const k = e.target.closest('button')?.dataset.mode; if (k) { state.mode = k; ml.setMode(k); renderAll(); } };
$('#views').onclick = e => { const v = e.target.closest('button')?.dataset.view; if (v) { state.view = v; renderAll(); } };
$('#months').onclick = e => { const i = e.target.closest('button')?.dataset.i; if (i != null) { state.month = +i; ml.setMonth(state.month); renderAll(); } };
$('#months').onkeydown = e => {
  const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
  if (d) { state.month = (state.month + d + 6) % 6; ml.setMonth(state.month); renderAll(); $(`#months [data-i="${state.month}"]`).focus(); }
};

// ---------------------------------------------------------------- render

function renderControls() {
  for (const b of document.querySelectorAll('#modes button')) b.setAttribute('aria-checked', b.dataset.mode === state.mode);
  for (const b of document.querySelectorAll('#views button')) b.setAttribute('aria-checked', b.dataset.view === state.view);
  $('#months').innerHTML = issueObj().months.map((ym, i) => {
    const [m, y] = monthName(ym);
    return `<button role="radio" data-i="${i}" aria-checked="${i === state.month}" tabindex="${i === state.month ? 0 : -1}">${m}<small>${y}</small></button>`;
  }).join('');
  const iss = issueObj();
  $('#issue-meta').textContent = `${iss.label} issue · trained to ${data.meta.training_through} · ${iss.uses_partial_month ? 'uses 1–21 Oct and carried-forward climate indices' : 'complete months only'}`;
  $('#table-view').hidden = state.view !== 'table';
}

function renderLegend() {
  const m = MODES[state.mode];
  const span = m.domain[1] - m.domain[0];
  const grad = m.stops.map(([v, c]) => `${c} ${((v - m.domain[0]) / span) * 100}%`).join(',');
  $('#legend').innerHTML = `
    <h3>${m.label}${m.unit === '°C' ? ' · °C' : ''}</h3>
    <div class="bar" style="background:linear-gradient(90deg,${grad})"></div>
    <div class="ticks">${m.ticks.map(t => `<span>${state.mode === 'prob' ? Math.round(t * 100) + '%' : t}</span>`).join('')}</div>
    <div class="key"><span class="sw" style="background:#ef9a86;opacity:.35;outline:1px solid #e4e3df"></span>Faded: little hindcast skill at this lead (&lt;${LOW_SKILL})</div>
    <p>1° cells · ML ensemble (ridge + LightGBM) · experimental, not a Copernicus or BoM product. Monthly means only, not heatwave counts.</p>`;
}

function fmtMode(mode, m) { return MODES[mode].fmt({ temp: m.temp, anom: m.anom, prob: m.prob }[mode]); }

function renderPanel(s = cellSummary(data, state.issue, state.cell)) {
  if (!s) { $('#panel').innerHTML = '<p class="muted">Select a cell on the map.</p>'; return; }
  const m = s.months[state.month];
  const [mn, yr] = monthName(m.month);
  const vals = s.months.map(x => ({ temp: x.temp, anom: x.anom, prob: x.prob }[state.mode]));
  const lo = state.mode === 'temp' ? Math.min(...vals) - 2 : state.mode === 'anom' ? Math.min(0, ...vals) : 0;
  const hi = Math.max(...vals, state.mode === 'prob' ? 1 : lo + 0.5);
  $('#panel').innerHTML = `
    <h2>${s.locality ?? 'Grid cell'}</h2>
    <p class="sub">${cellName(s)} · ${s.issue.label} issue</p>
    <div class="muted">${MODES[state.mode].label}, ${mn} ${yr}</div>
    <div class="big"><b>${fmtMode(state.mode, m)}</b><span>lead ${m.lead}</span></div>
    <dl class="kv">
      <dt>Forecast monthly mean</dt><dd>${m.temp.toFixed(1)} °C</dd>
      <dt>80% range</dt><dd>${m.lo.toFixed(1)}–${m.hi.toFixed(1)} °C</dd>
      <dt>1991–2020 average</dt><dd>${m.normal.toFixed(1)} °C</dd>
      <dt>Difference</dt><dd>${MODES.anom.fmt(m.anom)}</dd>
      <dt>Chance warmer than average</dt><dd>${MODES.prob.fmt(m.prob)}</dd>
      <dt>Hindcast skill here (lead ${m.lead})</dt><dd>${skillWord(m.skill)} (${m.skill.toFixed(2)})</dd>
    </dl>
    <div class="muted">${MODES[state.mode].label}, all six months</div>
    <div class="bars">${s.months.map((x, i) => {
      const h = Math.max(2, ((vals[i] - lo) / (hi - lo)) * 100);
      return `<div class="${i === state.month ? 'on' : ''} ${x.lowSkill ? 'low' : ''}">${fmtMode(state.mode, x)}<span class="b" style="height:${h}%"></span></div>`;
    }).join('')}</div>
    <div class="months-lbl">${s.months.map(x => `<span>${monthName(x.month)[0]}</span>`).join('')}</div>
    ${m.lowSkill ? `<div class="note">The 2006–2025 hindcast showed little skill for this cell at lead ${m.lead}. Treat this value as close to the long-term normal.</div>` : ''}
    <div class="note">Planning context only. A warmer month raises the background odds of hot days; it does not forecast heatwaves or their dates. Use the Short-term Heatwave Planner (Q1) for the next seven days.</div>
    <hr>
    <p class="muted">Model: ${data.meta.model}. Source: ${data.meta.source}. Spread from out-of-sample hindcast errors (σ ${data.meta.sigma_by_lead[m.lead]} °C at lead ${m.lead}); probabilities calibrated on 2011–2025. Compare anomalies, not absolute °C, with Copernicus: the two use different reference data.</p>`;
}

function renderTable() {
  if (state.view !== 'table') return;
  const iss = issueObj();
  const rows = data.localities.map(l => {
    const s = cellSummary(data, state.issue, l.cell);
    return `<tr><td>${l.name}</td>${s.months.map((m, i) => `<td class="${i === state.month ? 'sel' : ''}">${fmtMode(state.mode, m)}${m.lowSkill ? '*' : ''}</td>`).join('')}</tr>`;
  }).join('');
  $('#table-view').innerHTML = `
    <table><caption class="muted" style="text-align:left;padding-bottom:8px">${MODES[state.mode].label} by locality cell, ${iss.label} issue. * little hindcast skill at that lead.
      All 255 cells: <a href="../outputs/forecast_grid.csv">forecast_grid.csv</a></caption>
    <thead><tr><th>Locality</th>${iss.months.map(ym => `<th>${monthName(ym).join(' ')}</th>`).join('')}</tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function renderAll() { renderControls(); renderLegend(); renderPanel(); renderTable(); syncUrl(); }

renderAll();
ml.select(state.cell);

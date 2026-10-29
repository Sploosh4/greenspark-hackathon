// ML seasonal outlook as a MapLibre layer.
//
// Drop-in for any MapLibre map (e.g. the Team Connect "WA community outlook" screen):
//   import { addMlOutlookLayer } from './ml-outlook-layer.mjs';
//   const data = await (await fetch('ml_outlook_layer.json')).json();
//   const ml = addMlOutlookLayer(map, data, { mode: 'anom', issue: '2026-11', month: 0, onSelect: showCell });
//   ml.setMonth(2); ml.setMode('prob'); ml.setIssue('2026-10'); ml.select('-18.5_125.5');
//
// Data comes from export_map_layer.py. Cells are 1-degree squares built here from their centres, so the
// layer never claims finer resolution than the model has. Cells where the hindcast showed little skill at
// the selected lead are drawn faded and flagged, rather than coloured with the same confidence.

export const LOW_SKILL = 0.05;

// One fixed scale per measure, shared across months, issues and areas (Q3 display rules).
export const MODES = {
  temp: {
    label: 'Monthly mean temperature', unit: '°C', key: 't', domain: [14, 36],
    stops: [[14, '#4f86c0'], [20, '#a6cbe3'], [26, '#f4e7a8'], [32, '#ec8a52'], [36, '#c3372b']],
    ticks: [14, 20, 26, 32, 36], fmt: v => `${v.toFixed(1)} °C`,
  },
  anom: {
    label: 'Difference from 1991–2020 average', unit: '°C', key: 'a', domain: [-3, 3],
    stops: [[-3, '#184f95'], [-1.5, '#86b6ef'], [0, '#f0efec'], [1.5, '#ef9a86'], [3, '#a8231f']],
    ticks: [-3, -1.5, 0, 1.5, 3], fmt: v => `${v >= 0 ? '+' : ''}${v.toFixed(1)} °C`,
  },
  prob: {
    label: 'Chance of warmer than 1991–2020 average', unit: '%', key: 'p', domain: [0, 1],
    stops: [[0, '#184f95'], [0.3, '#86b6ef'], [0.5, '#f0efec'], [0.7, '#ef9a86'], [1, '#a8231f']],
    ticks: [0, 0.25, 0.5, 0.75, 1], fmt: v => `${Math.round(v * 100)}%`,
  },
};

const NO_DATA = '#cfcfcb';
const SRC = 'ml-outlook';

/** GeoJSON squares for one issue; properties t0..t5, a0..a5, p0..p5, s0..s5 index the six lead months. */
export function cellsToGeoJSON(data, issue) {
  return {
    type: 'FeatureCollection',
    features: data.cells.map(c => {
      const f = c.f[issue];
      const props = { id: c.id, lat: c.lat, lon: c.lon };
      for (let i = 0; i < 6; i++) {
        props[`t${i}`] = f ? f.t[i] : null;
        props[`a${i}`] = f ? f.a[i] : null;
        props[`p${i}`] = f ? f.p[i] : null;
        props[`s${i}`] = c.skill[i];
      }
      const [w, e, s, n] = [c.lon - 0.5, c.lon + 0.5, c.lat - 0.5, c.lat + 0.5];
      return { type: 'Feature', id: data.cells.indexOf(c), properties: props,
        geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
    }),
  };
}

function colourExpr(mode, i) {
  const m = MODES[mode];
  const v = ['get', `${m.key}${i}`];
  return ['case', ['==', v, null], NO_DATA, ['interpolate', ['linear'], v, ...m.stops.flat()]];
}

/** Summary of one cell for a side panel: all six months plus range, normal and hindcast skill. */
export function cellSummary(data, issue, id) {
  const c = data.cells.find(x => x.id === id);
  const iss = data.issues.find(x => x.key === issue);
  if (!c || !iss) return null;
  const f = c.f[issue];
  const locality = data.localities.find(l => l.cell === id)?.name ?? null;
  return {
    id, locality, lat: c.lat, lon: c.lon, issue: iss,
    months: iss.months.map((month, i) => ({
      month, lead: i + 1, temp: f.t[i], anom: f.a[i], prob: f.p[i], lo: f.lo[i], hi: f.hi[i], normal: f.n[i],
      skill: c.skill[i], lowSkill: c.skill[i] < LOW_SKILL,
    })),
  };
}

export function skillWord(s) {
  return s >= 0.15 ? 'good' : s >= LOW_SKILL ? 'modest' : 'little or none';
}

export function addMlOutlookLayer(map, data, opts = {}) {
  let { issue = data.issues.at(-1).key, month = 0, mode = 'anom', beforeId, onSelect = () => {}, onHover = () => {} } = opts;
  let selected = null;
  const idIndex = new Map(data.cells.map((c, i) => [c.id, i]));

  map.addSource(SRC, { type: 'geojson', data: cellsToGeoJSON(data, issue),
    attribution: 'ML outlook: NASA POWER (MERRA-2), NOAA CPC indices · experimental' });
  map.addLayer({ id: `${SRC}-fill`, type: 'fill', source: SRC, paint: {
    'fill-color': colourExpr(mode, month),
    'fill-opacity': ['case', ['<', ['get', `s${month}`], LOW_SKILL], 0.35, 0.85],
  } }, beforeId);
  map.addLayer({ id: `${SRC}-line`, type: 'line', source: SRC, paint: {
    'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], '#1b2a22', '#ffffff'],
    'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2.5, 0.4],
  } }, beforeId);

  const repaint = () => {
    map.setPaintProperty(`${SRC}-fill`, 'fill-color', colourExpr(mode, month));
    map.setPaintProperty(`${SRC}-fill`, 'fill-opacity', ['case', ['<', ['get', `s${month}`], LOW_SKILL], 0.35, 0.85]);
  };
  const select = id => {
    if (selected != null) map.setFeatureState({ source: SRC, id: selected }, { selected: false });
    selected = idIndex.has(id) ? idIndex.get(id) : null;
    if (selected != null) map.setFeatureState({ source: SRC, id: selected }, { selected: true });
    onSelect(selected != null ? cellSummary(data, issue, id) : null);
  };

  const click = e => e.features?.length && select(e.features[0].properties.id);
  const move = e => {
    map.getCanvas().style.cursor = e.features?.length ? 'pointer' : '';
    onHover(e.features?.length ? { point: e.point, cell: cellSummary(data, issue, e.features[0].properties.id), month } : null);
  };
  const leave = () => { map.getCanvas().style.cursor = ''; onHover(null); };
  map.on('click', `${SRC}-fill`, click);
  map.on('mousemove', `${SRC}-fill`, move);
  map.on('mouseleave', `${SRC}-fill`, leave);

  return {
    get state() { return { issue, month, mode }; },
    setMode(m) { mode = m; repaint(); },
    setMonth(i) { month = i; repaint(); },
    setIssue(k) {
      issue = k;
      map.getSource(SRC).setData(cellsToGeoJSON(data, issue));
      if (selected != null) select(data.cells[selected].id);
    },
    select,
    remove() {
      map.off('click', `${SRC}-fill`, click); map.off('mousemove', `${SRC}-fill`, move); map.off('mouseleave', `${SRC}-fill`, leave);
      for (const l of [`${SRC}-line`, `${SRC}-fill`]) if (map.getLayer(l)) map.removeLayer(l);
      if (map.getSource(SRC)) map.removeSource(SRC);
    },
  };
}

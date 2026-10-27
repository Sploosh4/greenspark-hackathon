// Vercel port of the serve-demo.py MapTiler proxy: allowlisted paths, key attached upstream only.
const MAP_ROOTS = new Set(['maps', 'tiles', 'fonts', 'sprites', 'resources']);
const MAX_RESOURCE_BYTES = 16 * 1024 * 1024;

const json = (value, status) => new Response(JSON.stringify(value), {
  status, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'},
});

// Keep style, TileJSON, glyphs and sprites same-origin; omit upstream keys.
function rewriteMapUrls(value, origin) {
  if (Array.isArray(value)) return value.map(item => rewriteMapUrls(item, origin));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rewriteMapUrls(item, origin)]));
  }
  if (typeof value === 'string' && value.startsWith('https://api.maptiler.com/')) {
    const parsed = new URL(value);
    parsed.searchParams.delete('key');
    parsed.searchParams.append('demo_v', '1');
    return origin + '/maptiler' + decodeURI(parsed.pathname) + parsed.search;
  }
  return value;
}

export async function GET(request) {
  const key = process.env.MAPTILER_API_KEY || '';
  if (!key) return json({error: 'Map key unavailable'}, 503);
  if (request.headers.get('sec-fetch-site') === 'cross-site') return json({error: 'Same-origin request required'}, 403);

  const url = new URL(request.url);
  const path = url.searchParams.get('mtpath') || '';
  let decoded;
  try { decoded = decodeURIComponent(path); } catch { return json({error: 'Map resource not allowed'}, 404); }
  // No user-supplied host, traversal, credential or arbitrary upstream route.
  if (path.length > 1800 || !MAP_ROOTS.has(decoded.split('/')[0]) ||
      decoded.split('/').some(part => part === '.' || part === '..') ||
      !/^[\w /.,@+%{}\-]+$/u.test(decoded) || decoded.includes('\\')) {
    return json({error: 'Map resource not allowed'}, 404);
  }

  const host = request.headers.get('x-forwarded-host') || request.headers.get('host') || url.host;
  const origin = `${request.headers.get('x-forwarded-proto') || 'https'}://${host}`;
  const query = new URLSearchParams();
  for (const name of ['language', 'variant']) if (url.searchParams.has(name)) query.set(name, url.searchParams.get(name));
  query.set('key', key);
  // encodeURI keeps '@' (sprite@2x) and ',' (font stacks) literal, as MapTiler expects.
  const upstreamPath = encodeURI(decoded);

  try {
    const response = await fetch(`https://api.maptiler.com/${upstreamPath}?${query}`, {
      headers: {Referer: origin + '/', Origin: origin, 'User-Agent': 'TeamConnectVercelDemo/1.0'},
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error(`Upstream ${response.status}`);
    let payload = new Uint8Array(await response.arrayBuffer());
    let contentType = response.headers.get('content-type') || 'application/octet-stream';
    if (payload.byteLength > MAX_RESOURCE_BYTES) throw new Error('Oversized map resource');
    const isJson = contentType.includes('json') || decoded.endsWith('.json');
    if (isJson) {
      const document = JSON.parse(new TextDecoder().decode(payload));
      if (decoded === 'maps/streets-v4/style.json') {
        // The provider's generic road shield expression needs a route ref.
        // Keep unnumbered streets in road/name layers, without an empty shield.
        for (const layer of document.layers || []) {
          if (layer.id === 'Road shields') {
            layer.filter = ['all', layer.filter, ['has', 'ref_length'],
              ['>', ['to-number', ['get', 'ref_length'], 0], 0]];
          }
        }
      }
      const text = JSON.stringify(rewriteMapUrls(document, origin));
      if (text.includes(key)) throw new Error('Unexpected credential in upstream JSON');
      payload = new TextEncoder().encode(text);
      contentType = 'application/json';
    }
    return new Response(payload, {headers: {
      'Content-Type': contentType,
      'Cache-Control': isJson ? 'public, max-age=300, s-maxage=3600' : 'public, max-age=3600, s-maxage=86400',
      'X-Content-Type-Options': 'nosniff',
    }});
  } catch {
    // Never return upstream bodies, exception text, or credential-bearing URLs.
    return json({error: 'Basemap resource unavailable'}, 502);
  }
}

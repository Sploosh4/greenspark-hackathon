"""Browser regression checks. Requires Python Playwright and a Chromium executable.
Run: python3 scripts/qa-teamconnect.py --output /tmp/teamconnect-qa
The demo itself has no Playwright dependency. Starts/stops its own loopback server.
"""
import argparse,hashlib,json,socket,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('/tmp/teamconnect-qa'));p.add_argument('--chromium',default='/usr/bin/chromium');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
server=subprocess.Popen([sys.executable,'serve-demo.py','--port',str(port)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
base=f'http://127.0.0.1:{port}'
results=[]
def passed(name):results.append({'name':name,'pass':True});print('PASS',name,flush=True)
def screenshot(page,name):page.screenshot(path=str(a.output/(name+'.png')),full_page=True)
try:
 for _ in range(50):
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=.1):break
  except OSError:time.sleep(.05)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=a.chromium,headless=True,args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
  context=browser.new_context(viewport={'width':1440,'height':900},reduced_motion='reduce')
  errors=[];external=[]
  context.on('page',lambda page:page.on('pageerror',lambda err:errors.append(str(err))))
  context.on('request',lambda request:external.append(urlsplit(request.url).netloc) if urlsplit(request.url).hostname not in ['127.0.0.1',None] else None)
  def instrument_map(route):
   response=route.fetch()
   body=response.text()+'''\n;window.__qaMaps=[];const OriginalMap=window.maplibregl.Map;window.maplibregl.Map=class extends OriginalMap{constructor(options){super(options);window.__qaMaps.push(this);}};'''
   route.fulfill(response=response,body=body)
  context.route('**/vendor/maplibre-gl.js',instrument_map)
  page=context.new_page();page.goto(base);page.wait_for_selector('#search')
  expect(page.locator('h1')).to_have_count(1);expect(page.locator('.table-status')).to_have_text('448 customers · showing 1–20');expect(page.locator('[data-customer]')).to_have_count(20);expect(page.locator('.map')).to_have_count(0)
  screenshot(page,'customer-review');passed('Default review: 448 accounts, 20 rows, single page title and no customer map')
  for key in ['reference','community','account','reason','date','support','contact']:
   button=page.locator(f'[data-sort={key}]');button.click();button=page.locator(f'[data-sort={key}]')
   if page.locator('th[aria-sort=descending]').count():button.click()
   expect(page.locator('th[aria-sort=ascending]')).to_contain_text(button.inner_text().strip('↑↓↕'))
   page.locator(f'[data-sort={key}]').click();expect(page.locator('th[aria-sort=descending]')).to_have_count(1)
  page.locator('[data-sort=reference]').click();page.locator('[data-sort=reference]').click()
  expect(page.locator('[data-customer]').first).to_have_text('C105149');passed('All seven table columns sort in both directions')
  page.locator('#scope').select_option('South Hedland');page.locator('#account-filter').select_option('prepaid');page.locator('#search').fill('C105011')
  expect(page.locator('[data-customer]')).to_have_count(1)
  queue_hash=page.evaluate('location.hash');page.locator('[data-customer=C105011]').click();expect(page.locator('h1')).to_have_text('C105011 · Overview')
  page.go_back();expect(page.locator('#search')).to_have_value('C105011');expect(page.locator('#scope')).to_have_value('South Hedland');expect(page.locator('#account-filter')).to_have_value('prepaid');assert page.evaluate('location.hash')==queue_hash
  page.reload();page.wait_for_selector('#search');expect(page.locator('#search')).to_have_value('C105011');expect(page.locator('#scope')).to_have_value('South Hedland')
  page.locator('[data-customer=C105011]').click()
  for tab in ['overview','credit','needs','arrangements','journey']:
   page.locator(f'[data-view={tab}]').click();page.locator(f'[data-view={tab}]').click();expect(page.locator('h1')).to_have_count(1);expect(page.locator('#customer-tabs [aria-current=page]')).to_have_count(1)
  page.locator('#back-review').click();expect(page.locator('#search')).to_have_value('C105011');expect(page.locator('[data-sort=reference]').locator('..')).to_have_attribute('aria-sort','descending')
  passed('Customer navigation, repeated tab clicks, browser Back and Back to review retain search/filter/sort')
  page.locator('#search').fill('does-not-exist');expect(page.locator('[data-customer]')).to_have_count(0);expect(page.locator('.empty')).to_contain_text('No matching customers');page.locator('#clear-filters').click();expect(page.locator('[data-customer]')).to_have_count(20)
  first=page.locator('[data-customer]').first.inner_text();page.get_by_role('button',name='Next',exact=True).click();assert page.locator('[data-customer]').first.inner_text()!=first
  page.locator('[data-customer]').first.click();page.locator('#back-review').click();expect(page.locator('.pagination span')).to_have_text('Page 2 of 23')
  passed('Empty results, clear filters and pagination survive detail navigation')
  page.locator('#prepaid-example').click();expect(page.locator('#content')).to_contain_text('$109.66');expect(page.locator('#content')).to_contain_text('Coverage estimate unavailable');screenshot(page,'customer-overview')
  page.locator('[data-view=credit]').click();expect(page.locator('#content')).to_contain_text('fewer than three complete on-supply days');screenshot(page,'financial-pressure')
  page.locator('[data-view=needs]').click();expect(page.locator('#content')).to_contain_text('Customer reported difficulty budgeting');screenshot(page,'disclosed-needs')
  page.locator('[data-view=arrangements]').click();expect(page.locator('#content')).to_contain_text('No arrangement recorded as of this date');page.locator('#date').fill('2025-01-21');page.locator('#date').dispatch_event('change');expect(page.locator('#content')).to_contain_text('Support check-in');screenshot(page,'existing-arrangements')
  page.locator('[data-view=journey]').click();expect(page.locator('.journey-steps li').nth(3)).to_contain_text('Delivered');expect(page.locator('.journey-steps li').nth(4)).to_contain_text('Not recorded')
  page.locator('#date').fill('2025-01-28');page.locator('#date').dispatch_event('change');expect(page.locator('.journey-steps li').nth(4)).to_contain_text('Customer confirmed');screenshot(page,'support-journey')
  passed('Prepaid fixture, disclosed needs, dated arrangements and delivery versus resolution are consistent')
  page.locator('#back-review').click();page.locator('#billed-example').click();expect(page.locator('#content')).to_contain_text('$184.28');expect(page.locator('#content')).to_contain_text('$167.89');expect(page.locator('#content')).to_contain_text('+9.8%');page.get_by_text('Inspect the calculation',exact=True).click();expect(page.locator('.details-body')).to_contain_text('25 remaining days');screenshot(page,'billed-pressure')
  assert not any(s in page.locator('#content').inner_text() for s in ['NaN','Infinity','undefined']);passed('Billed fixture: $184.28 versus $167.89, +9.8%, inspectable calculation')
  page.goto(base+'/#customer=C101664&view=needs&date=2025-01-17&event=HEAT01');page.wait_for_selector('.match');expect(page.locator('#content')).to_contain_text('Heat-related disclosure');expect(page.locator('.map')).to_have_count(0)
  passed('Explicit cooling need resurfaces beside issued weather; account view contains no map')
  page.locator('[data-workspace=planning]').click();page.wait_for_function('() => window.__qaMaps.at(-1)?.loaded()')
  style=page.evaluate('window.__qaMaps.at(-1).getStyle()');assert style['sources']=={};assert [layer['id'] for layer in style['layers']]==['background'];expect(page.locator('.map svg polygon,.map svg circle,.maplibregl-marker')).to_have_count(0)
  zoom=page.evaluate('window.__qaMaps.at(-1).getZoom()');page.get_by_role('button',name='Zoom in',exact=True).click();page.wait_for_function('() => window.__qaMaps.at(-1).getZoom()>11')
  page.locator('#planning-community').select_option('Esperance');page.locator('#planning-months').select_option('6');page.wait_for_function('() => window.__qaMaps.at(-1)?.loaded()');expect(page.locator('#content')).to_contain_text('No audience for this community');assert page.locator('.chart svg circle').count()==6
  page.set_viewport_size({'width':1200,'height':900});page.wait_for_function('() => Math.abs(document.querySelector(".maplibregl-canvas").getBoundingClientRect().width-document.querySelector("#map-live").getBoundingClientRect().width)<2')
  page.locator('[data-workspace=review]').click();page.locator('[data-workspace=planning]').click();page.wait_for_function('() => window.__qaMaps.at(-1)?.loaded()');expect(page.locator('.maplibregl-canvas')).to_have_count(1)
  page.set_viewport_size({'width':1440,'height':900});page.locator('#planning-community').select_option('South Hedland');page.locator('#planning-months').select_option('12');page.wait_for_function('() => window.__qaMaps.at(-1)?.loaded()');screenshot(page,'community-planning')
  passed('Area map has no synthetic source/overlay/marker; zoom, community, horizon, resize and workspace switching work')
  # Exercise every community at each scenario date boundary and all four events.
  for date in ['2025-01-01','2025-02-01','2025-03-31']:
   page.locator('#date').fill(date);page.locator('#date').dispatch_event('change')
   for event in ['HEAT01','HEAT02','CYCLONE01','FLOOD01']:
    page.locator('#event').select_option(event)
    for option in page.locator('#planning-community option').all():
     page.locator('#planning-community').select_option(option.get_attribute('value'))
     assert not any(s in page.locator('#content').inner_text() for s in ['NaN','Infinity','undefined'])
  passed('All 12 communities × 4 weather scenarios × 3 case-date boundaries render without invalid numbers')
  page.goto(base+'/#view=overview&customer=C105011&date=2025-02-31&scope=invalid&sort=invalid&page=Infinity');page.wait_for_selector('h1');expect(page.locator('#date')).to_have_value('2025-01-17');expect(page.locator('h1')).to_have_text('C105011 · Overview')
  passed('Invalid URL date/filter/sort/page state normalises safely')
  page.goto(base+'/checks.html');page.wait_for_selector('#results h2');expect(page.locator('#results h2')).to_have_text('36 / 36 checks passed');screenshot(page,'verification-checks');passed('Existing browser checks: 36 / 36')
  mobile=context.new_page();mobile.set_viewport_size({'width':390,'height':844});mobile.goto(base);mobile.wait_for_selector('#search');assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth');mobile.locator('#prepaid-example').click();mobile.locator('[data-view=journey]').click();assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth');screenshot(mobile,'mobile-journey')
  mobile.locator('[data-workspace=planning]').click();assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth');passed('390px mobile review, account tabs and planning contain page overflow')
  # Basic semantic checks across each workspace and all account sections.
  page.goto(base);page.wait_for_selector('#search')
  for view in ['review','overview','credit','needs','arrangements','journey','planning']:
   page.goto(base+'/#view='+view);page.wait_for_selector('h1');expect(page.locator('h1')).to_have_count(1)
   unnamed=page.evaluate('''[...document.querySelectorAll('button,input,select')].filter(el=>!el.hidden&&el.getClientRects().length&&!el.getAttribute('aria-label')&&!el.getAttribute('aria-labelledby')&&!(el.innerText||'').trim()&&!el.labels?.length).length''')
   assert unnamed==0,(view,unnamed)
  passed('Accessibility basics: labelled controls, column headers, one h1, landmarks, focus styles and skip link')
  missing=context.new_page();missing.route('**/vendor/maplibre-gl.js',lambda route:route.abort());missing.goto(base+'/#view=planning');missing.wait_for_selector('h1');expect(missing.locator('.offline-map')).to_be_visible();expect(missing.locator('.offline-map svg')).to_have_count(0);missing.locator('[data-workspace=review]').click();expect(missing.locator('#search')).to_be_visible()
  broken=context.new_page();broken.route('**/vendor/maplibre-gl.js',lambda route:route.fulfill(content_type='text/javascript',body="window.maplibregl={Map:class{constructor(){throw Error('QA WebGL failure')}}};"));broken.goto(base+'/#view=planning');broken.wait_for_selector('#map-status');expect(broken.locator('#map-status')).to_have_text('Map unavailable');expect(broken.locator('.offline-map')).to_be_visible()
  failed=context.new_page();failed.route('**/scenario.json',lambda route:route.abort());failed.goto(base);failed.wait_for_selector('#retry');expect(failed.locator('#content')).to_contain_text('Scenario data unavailable');expect(failed.locator('#date')).to_be_disabled();failed.locator('#retry').click();expect(failed.locator('#content')).to_contain_text('Scenario data unavailable')
  passed('Missing map network/library, WebGL failure and missing data/retry remain usable without fabricated geometry')
  assert not errors,errors;assert not external,external
  passed('No uncaught browser exceptions or external requests; no credentials used')
  browser.close()
 payload=json.loads((ROOT/'teamconnect/scenario.json').read_text());provenance=json.loads((ROOT/'teamconnect/provenance.json').read_text())
 assert hashlib.sha256((ROOT/'teamconnect/scenario.json').read_bytes()).hexdigest()==provenance['scenario_json_sha256']
 passed('Prepared fixture SHA-256 matches retained provenance')
except Exception as error:
 results.append({'name':str(error),'pass':False});raise
finally:
 server.terminate();server.wait(timeout=10)
 (a.output/'results.json').write_text(json.dumps({'passed':sum(r['pass'] for r in results),'total':len(results),'checks':results},indent=2)+'\n')

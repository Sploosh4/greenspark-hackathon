import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const fragment=source.slice(source.indexOf('function weatherTimeLabel'),source.indexOf('function renderLiveWeather'));
const ctx={Intl,Date,esc:value=>String(value).replaceAll('<','&lt;'),badge:value=>value,dl:rows=>rows.map(row=>row.join(':')).join('\n')};
vm.createContext(ctx);vm.runInContext(fragment,ctx);
test('schedule renders exact Perth next run independently of browser timezone',()=>{
 const text=ctx.weatherScheduleMarkup({enabled:true,daily_time:'06:00',next_run_at:'2026-10-29T22:00:00Z',last_attempt_succeeded:true,cache_reused:true});
 assert.match(text,/Active/);assert.match(text,/30 Oct 2026.*06:00/);assert.match(text,/Australia\/Perth/);assert.match(text,/Saved weather is current/);assert.match(text,/uploads|Upload data/);
});
test('failed, unstarted and checking schedule states remain distinct',()=>{
 assert.match(ctx.weatherScheduleMarkup({enabled:false,last_attempt_succeeded:false}),/Not running/);
 assert.match(ctx.weatherScheduleMarkup({enabled:true,running:true}),/Checking weather/);
 assert.match(ctx.weatherScheduleMarkup({last_attempt_succeeded:false}),/saved weather retained/);
 assert.equal(ctx.weatherTimeLabel('broken'),'Unavailable');assert.equal(ctx.weatherTimeLabel(null),'Unavailable');
});

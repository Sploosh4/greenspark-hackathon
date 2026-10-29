// Opt-in local measurement only; no telemetry or account/source values logged.
export const PERF=typeof location!=='undefined'&&new URLSearchParams(location.search).get('perf')==='1';
export function painted(kind,start,extra={}){
 if(!PERF)return Promise.resolve();
 return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
  console.info('Q3 performance '+JSON.stringify({kind,durationMs:performance.now()-start,...extra}));resolve();
 })));
}

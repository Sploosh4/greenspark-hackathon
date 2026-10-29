import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import vm from 'node:vm';
const source=readFileSync(new URL('../app.mjs',import.meta.url),'utf8');
const money=source.slice(source.indexOf('const money='),source.indexOf('const badge='));
test('optional blank financial amounts remain unavailable and genuine zero remains money',()=>{
 const values=vm.runInNewContext(money+"\n[null,'',undefined,0,'0',12.3].map(money)",{Intl});
 assert.deepEqual(Array.from(values),['Unavailable','Unavailable','Unavailable','$0.00','$0.00','$12.30']);
});

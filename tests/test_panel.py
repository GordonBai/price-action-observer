"""Real Chromium DOM checks; skipped if optional Playwright/Chromium is absent."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class PanelTests(unittest.TestCase):
    def test_candles_filters_causal_focus_and_safe_sources(self):
        node=shutil.which('node'); browser=shutil.which('chromium')
        if not node or not browser:self.skipTest('optional Node/Chromium unavailable')
        probe=subprocess.run([node,'-e',"require('playwright')"],capture_output=True)
        if probe.returncode:self.skipTest('optional Playwright unavailable')
        script=r'''
const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.argv[1],args:['--no-sandbox']});
 try {
 const page=await browser.newPage();
 const bars=[0,1,2].map((n)=>({time:`2026-11-17T14:3${n+1}:00+00:00`,open:10+n,high:12+n,low:9+n,close:11+n}));
 const events=[{id:'a',observed_at:bars[1].time,family:'inside_bar',status:'observed',direction:'neutral',explanation:'安全文字 <script>window.pwned=true</script>',anchors:{first_time:bars[0].time,level:10},knowledge_version:'abc',uncertainty:'不确定性',knowledge_references:[{title:'内包',summary:'知识',counterexample:'反例',source_urls:['https://example.com/source','javascript:alert(1)']}]},{id:'b',observed_at:bars[2].time,family:'double_bottom',status:'candidate',direction:'long',explanation:'双底候选'}];
 const stream={symbol:'T',timeframe:'1',source:'fixture',bar_count:3,last_bar_close:bars[2].time,age_seconds:100,freshness:'HISTORICAL',bars,events,state:{knowledge_version:'abc'}};
 let calls=0;
 await page.route('**/snapshot',route=>{calls++;return route.fulfill({json:{streams:[stream,{...stream,symbol:'U',events:[],bars:[]}],notice:'测试快照'}})});
 await page.route('http://panel.test/',route=>route.fulfill({contentType:'text/html',body:fs.readFileSync(process.argv[2],'utf8')}));
 await page.goto('http://panel.test/');await page.locator('#token').fill('not-a-real-secret');await page.locator('#connect').click();
 await page.waitForFunction(()=>document.querySelectorAll('.candle-body').length===3);
 if(await page.locator('.candle-wick').count()!==3)throw Error('OHLC wicks absent');
 await page.selectOption('#family-filter','inside_bar');
 if(await page.locator('#events tr').count()!==1)throw Error('family filter failed');
 await page.locator('#events button').first().click();
 if(await page.locator('.candle-body').count()!==2)throw Error('event focus leaked future bars');
 if(!(await page.locator('#focus-info').innerText()).includes('14:32'))throw Error('focus time absent');
 if(await page.locator('#events a[href^="javascript:"]').count())throw Error('unsafe source URL');
 if(await page.evaluate(()=>window.pwned))throw Error('unsafe text');
 await page.locator('#clear-focus').click();
 if(await page.locator('.candle-body').count()!==3)throw Error('clear focus failed');
 await page.selectOption('#family-filter','');await page.selectOption('#status-filter','candidate');
 if(await page.locator('#events tr').count()!==1)throw Error('status filter failed');
 await page.selectOption('#streams','1');
 if(await page.locator('.candle-body').count())throw Error('stream change retained chart');
 await page.locator('#connect').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('U'));
 if(await page.inputValue('#streams')!=='1')throw Error('refresh lost stream identity');
 console.log(JSON.stringify({ok:true,calls}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
'''
        p=subprocess.run([node,'-e',script,browser,str(ROOT/'pa_lens/dashboard.html')],capture_output=True,text=True,timeout=40)
        if p.returncode and 'socket() failed: Operation not permitted' in p.stderr:
            self.skipTest('Chromium blocked by environment socket policy')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue(json.loads(p.stdout)['ok'])

    def test_render_logic_with_dom_fixture(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.value='';this.textContent='';this.listeners={};}
 setAttribute(k,v){this.attrs[k]=v;}
 append(...xs){this.children.push(...xs);}
 replaceChildren(...xs){this.children=xs;}
 addEventListener(k,v){this.listeners[k]=v;}
}
const elements={};
const document={getElementById:id=>elements[id]||(elements[id]=new Element('div')),createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t)};
const html=fs.readFileSync(process.argv[1],'utf8'),code=html.match(/<script>([\s\S]*)<\/script>/)[1];
const ctx={document,URL,console,setInterval:()=>0,fetch:()=>{throw Error('not called')}};vm.createContext(ctx);vm.runInContext(code,ctx);
const bars=[0,1,2].map(n=>({time:`2026-11-17T14:3${n+1}:00Z`,open:10+n,high:12+n,low:9+n,close:11+n}));
const events=[{id:'a',observed_at:bars[1].time,family:'inside_bar',status:'observed',anchors:{level:10},explanation:'<img src=x>',knowledge_references:[{title:'test',summary:'summary',counterexample:'counter',source_urls:['https://example.com','javascript:alert(1)'],sources:[{review_method:'sampled_frames',locator:'page 3',limitations:'audio not heard'}]}],uncertainty:'uncertain'},{id:'b',observed_at:bars[2].time,family:'double_bottom',status:'candidate'}];
ctx.fixture={native_indicators:{slot_count:2,items:[{symbol:'T',indicator_type:'macd',requested:{interval:'5minute',parameters:{}},returned_params:{fast_period:12},status:'AVAILABLE_SOURCE_UNKNOWN',latest:{time:'2026-11-17T14:35:00Z',values:{macd:'-1.2',signal:'0',histogram:null}},received_at:'2026-11-17T14:36:00Z',source_quality:'unknown',warmup:'unknown',points:[]},{symbol:'T',indicator_type:'supertrend',requested:{interval:'5minute',parameters:{}},status:'ERROR',latest:null,received_at:'2026-11-17T14:36:00Z',source_quality:'unknown',warmup:'unknown',points:[]}]},streams:[{symbol:'T',timeframe:'1',source:'fixture',bars,events,state:{}}]};
vm.runInContext('snapshot=fixture;render()',ctx);
function all(el,p){return [ ...(p(el)?[el]:[]), ...el.children.flatMap(x=>all(x,p)) ];}
function countCandles(){return all(elements.chart,x=>x.attrs.class==='candle-body').length}
assert.equal(countCandles(),3,'need OHLC candles');
assert(JSON.stringify(elements['native-indicators']).includes('histogram'), 'native multi-fields missing');
assert(JSON.stringify(elements['native-indicators']).includes('null'), 'null must not become zero');
assert(JSON.stringify(elements['native-indicators']).includes('ERROR'), 'failed request hidden');
ctx.fixture.streams[0].events.push({id:'basic',observed_at:bars[2].time,family:'trend_bar',status:'observed'});
vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,2,'basic features should hide by default');
elements['show-basic'].checked=true;vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,3,'all features toggle');elements['show-basic'].checked=false;
elements['family-filter'].value='inside_bar';vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,1);
all(elements.events,x=>x.tagName==='button')[0].listeners.click();assert.equal(countCandles(),2,'future bars must hide at event focus');
assert(elements['focus-info'].textContent.includes('14:32'));
assert.equal(elements['native-indicators'].children.length,0,'historical focus leaked later native values');
assert(elements['native-notice'].textContent.includes('历史定位隐藏原生快照'));
assert.equal(all(elements.events,x=>x.tagName==='a').length,1,'reject unsafe source URL');
assert(elements.context.textContent.includes('事件未保存语境'),'must not backfill latest context');
assert(all(elements.events,x=>x.textContent==='反例 / 边界：counter').length===1,'source counterexample absent');
assert(all(elements.events,x=>x.tagName==='pre'&&x.textContent.includes('audio not heard')).length===1,'source review boundary absent');
assert(all(elements.events,x=>x.tagName==='img').length===0,'text must not become markup');
elements['clear-focus'].listeners.click();assert.equal(countCandles(),3);assert(elements['native-indicators'].children.length>0,'native values not restored');
elements['family-filter'].value='';elements['status-filter'].value='candidate';vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,1);
// Default grouped mode combines multiple events at the same observed bar.
elements['family-filter'].value='';elements['status-filter'].value='';
ctx.fixture.streams[0].display={groups:[{observed_at:bars[1].time,events:[events[0],{...events[0],id:'a2',family:'ii'}],event_ids:['a','a2'],priority:2,contexts:[],context_note:'frozen'}],stats:{raw_events:3,displayed_events:2,displayed_groups:1,hidden_by_priority:1,hidden_by_cooldown:0,hidden_duplicate_ids:0,hidden_events:1,retained_groups:1},config:{min_priority:2,cooldown_minutes:15},presentation_version:'test'};
document.getElementById('event-mode').value='grouped';vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,1,'same-bar group must be one row');
assert(elements['display-stats'].textContent.includes('hidden_by_priority'),'show display filtering stats');
all(elements.events,x=>x.tagName==='button')[0].listeners.click();assert.equal(countCandles(),2,'group focus must hide future bars');
elements['clear-focus'].listeners.click();
elements['event-mode'].value='raw';elements['show-basic'].checked=false;vm.runInContext('render()',ctx);assert.equal(elements.events.children.length,3,'raw mode retains original events');
ctx.fixture.streams.push({symbol:'U',timeframe:'1',source:'fixture',bars:[],events:[],state:{}});
elements.streams.value='1';elements.streams.listeners.change();assert.equal(countCandles(),0,'stream must clear old chart');assert.equal(elements.events.children.length,0);
(async()=>{
 let resolves=[];ctx.fetch=()=>new Promise(r=>resolves.push(r));
 const first=vm.runInContext('refresh()',ctx),second=vm.runInContext('refresh()',ctx);
 const newer={streams:[{symbol:'U',timeframe:'1',source:'fixture',bars:[],events:[],state:{},freshness:'NEW'}]};
 resolves[1]({ok:true,json:async()=>newer});await second;
 resolves[0]({ok:true,json:async()=>ctx.fixture});await first;
 assert(elements.status.textContent.startsWith('NEW'),'stale response replaced newer snapshot');
 ctx.fetch=async()=>({ok:false,status:401});await vm.runInContext('refresh()',ctx);
 assert(elements.status.textContent.startsWith('DISCONNECTED'),'failure must mark stale display');
 assert(elements['native-notice'].textContent.startsWith('DISCONNECTED'),'native failure must explicitly mark stale');
 assert.equal(elements['native-indicators'].children.length,0,'stale native values must hide');
 assert(!JSON.stringify(elements).includes('not-a-real-secret'),'credential rendered in output');
 console.log('ok');
})().catch(e=>{console.error(e);process.exit(1)});
"""
        p=subprocess.run([node,'-e',script,str(ROOT/'pa_lens/dashboard.html')],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)

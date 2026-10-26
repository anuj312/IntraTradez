/* Run: node tests/test_stable_polling.mjs */
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const html = fs.readFileSync(new URL('../intraday-momentum-scanner.html', import.meta.url), 'utf8');
const start = html.indexOf('let scanRequestInFlight = false;');
const end = html.indexOf('document.querySelectorAll(".segmented")', start);
assert.ok(start >= 0 && end > start, 'scanner polling code found');
const code = html.slice(start, end);
const state = {
  liveRows: null, live: false, feedStatus: 'offline', universe: 'stocks',
  sectorFlow: null, niftyIndex: null, ticks: 0, lastTick: null,
  lastValidDay: null, lastValidUniverse: null, lastValidUpdateAt: 0,
  seedProgress: {done:0,total:0,errors:0}
};
let reply = null, fetchCalls = 0, renders = 0;
const ctx = { state, AbortController, URLSearchParams, Date, Intl, Number,
  Array, setTimeout, clearTimeout,
  fetch: async () => { fetchCalls++; if (reply instanceof Error) throw reply; return {ok: true,json: async () => reply}; },
  render: () => renders++, showToast: () => {} };
vm.createContext(ctx);
vm.runInContext(code, ctx);
const load = () => vm.runInContext('loadLiveData(false)', ctx);
const tick = new Date().toLocaleString('sv-SE', {timeZone: 'Asia/Kolkata'}).replace(' ', 'T') + '+05:30';
const good = {rows:[{symbol:'RELIANCE',ltp:100,direction:1}],status:'live',live:true,market_open:true,last_tick:tick,sector_flow:[{name:'ENERGY'}],ticks:200};
reply = good; await load();
assert.equal(state.feedStatus,'live');
assert.equal(state.liveRows.length,1);
const firstTime = state.lastValidUpdateAt;
reply = {rows:[],status:'waiting_for_ticks',live:false,market_open:true}; await load();
assert.equal(state.feedStatus,'delayed');
assert.equal(state.liveRows[0].symbol,'RELIANCE');
assert.equal(state.lastValidUpdateAt,firstTime);
reply = new Error('Network offline'); await load();
assert.equal(state.feedStatus,'delayed');
assert.equal(state.liveRows.length,1);
reply = {...good,rows:[{symbol:'TCS',ltp:200,direction:1}]}; await load();
assert.equal(state.feedStatus,'live');
assert.equal(state.liveRows[0].symbol,'TCS');
state.lastValidUpdateAt -= 121000;
reply = new Error('Network offline'); await load();
assert.equal(state.feedStatus,'offline');
assert.equal(state.liveRows,null);
reply = good; await load();
state.universe = 'index';
reply = {rows:[],status:'waiting_for_ticks',live:false,market_open:true}; await load();
assert.equal(state.liveRows,null, 'do not retain another universe’s rows');
assert.ok(fetchCalls >= 7);
assert.ok(renders >= 7);
console.log('PASS: retain brief outages, stale warning state, recovery, expiration, universe isolation.');

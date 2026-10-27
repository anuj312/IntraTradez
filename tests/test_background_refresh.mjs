/* Run: node tests/test_background_refresh.mjs */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../intraday-momentum-scanner.html', import.meta.url), 'utf8');

// Check the scan scheduler from the reference: one 5-second interval, no
// document.hidden gate, and the same API poll in background tabs.
const pollStart = html.indexOf('let scanTimer = null;');
const pollEnd = html.indexOf('// Positive/negative LTP percentages', pollStart);
assert.ok(pollStart >= 0 && pollEnd > pollStart, 'scan polling scheduler present');
const schedules = [];
const scanCalls = [];
const document = { hidden: false };
const pollCtx = {
  document,
  loadLiveData: (manual) => scanCalls.push(manual),
  setInterval: (callback, interval) => { schedules.push({callback, interval}); return schedules.length; },
  clearInterval: () => {}
};
vm.createContext(pollCtx);
vm.runInContext(html.slice(pollStart, pollEnd), pollCtx);
vm.runInContext('startScanPolling()', pollCtx);
assert.deepEqual(scanCalls, [true], 'start triggers one immediate scan');
assert.equal(schedules.length, 1, 'only one recurring scan interval');
assert.equal(schedules[0].interval, 5000, 'scan polling runs every 5 seconds');
schedules[0].callback();
assert.deepEqual(scanCalls, [true, false], 'visible tab polls');
document.hidden = true;
schedules[0].callback();
assert.deepEqual(scanCalls, [true, false, false], 'hidden tab still polls /api/scan');
vm.runInContext('startScanPolling()', pollCtx);
assert.equal(schedules.length, 1, 'no duplicate timers');
vm.runInContext('stopScanPolling()', pollCtx);

// Preserve visible-tab fast recovery, but remove the old hidden-tab health ping.
const resumeStart = html.indexOf('// Continuation-specific polling, separate from the established /api/scan timer.');
const resumeEnd = html.indexOf('// Start the scanner immediately.', resumeStart);
assert.ok(resumeStart >= 0 && resumeEnd > resumeStart, 'tab-return refresh module exists');
const timers = [], events = {}, windowEvents = {};
const counts = {scan: 0, continuation: 0, delayed: 0};
const now = Date.now();
const resumeDoc = {
  hidden: false,
  addEventListener: (name, callback) => {events[name] = callback;}
};
const win = {
  continuationSelected: true,
  addEventListener: (name, callback) => {windowEvents[name] = callback;}
};
const resumeState = {feedStatus:'live', lastValidUpdateAt: now - 40000};
const resumeCtx = {
  document: resumeDoc, window:win, state:resumeState, Date,
  setInterval:(callback, interval) => {timers.push({callback, interval}); return timers.length;},
  loadLiveData:() => counts.scan++,
  loadContinuationRadar:() => counts.continuation++,
  showFeedInterruption:() => counts.delayed++,
};
vm.createContext(resumeCtx);
vm.runInContext(html.slice(resumeStart, resumeEnd), resumeCtx);
assert.equal(timers.length, 1, 'only continuation timer remains in this module');
assert.equal(timers[0].interval, 15000, 'continuation timer unchanged');
assert.ok(events.visibilitychange && windowEvents.pageshow, 'return events wired');
assert.equal(html.includes('checkBackgroundConnection'), false, 'obsolete health-ping routine removed');
resumeDoc.hidden = true;
events.visibilitychange();
assert.equal(counts.scan, 0, 'tab becoming hidden does not issue an extra request');
await timers[0].callback();
assert.equal(counts.continuation, 0, 'continuation stays paused while hidden');
resumeDoc.hidden = false;
events.visibilitychange();
assert.equal(counts.delayed, 1, 'stale quotes marked delayed before refresh');
assert.equal(counts.scan, 1, 'immediate scan when returning to tab');
assert.equal(counts.continuation, 1, 'selected continuation refresh on return');
windowEvents.pageshow({persisted:true});
assert.equal(counts.scan, 2, 'BFCache restore also refreshes scan');
console.log('PASS: /api/scan every 5 seconds visible/hidden, no duplicate timers, recovery on tab return.');

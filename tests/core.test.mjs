import test from 'node:test';
import assert from 'node:assert/strict';
import { selectRecords, summarize, toCsv } from '../web/assets/core.js';

const records = [
  { code: '2330', name: '台積電', market: 'sii', status: 'reported', date: '2026-10-15', title: 'Q3財報', url: 'https://mopsov.twse.com.tw/' },
  { code: '2408', name: '南亞科', market: 'sii', status: 'self_reported', date: '2026-10-12', title: '自結', url: 'https://mopsov.twse.com.tw/' },
  { code: '3260', name: '威剛', market: 'otc', status: 'reported', date: '2026-11-02', title: 'Q3財報', url: 'https://mopsov.twse.com.tw/' },
];

test('combines keyword, market, status and month filters instead of ignoring any', () => {
  assert.deepEqual(selectRecords(records, { query: '  台積  ', market: 'sii', status: 'reported', month: '2026-10' }).map(r => r.code), ['2330']);
  assert.deepEqual(selectRecords(records, { query: '326', market: 'sii' }), []);
});
test('sorts actual dates and codes consistently', () => {
  assert.deepEqual(selectRecords(records, { sort: 'newest' }).map(r => r.code), ['3260', '2330', '2408']);
  assert.deepEqual(selectRecords(records, { sort: 'oldest' }).map(r => r.code), ['2408', '2330', '3260']);
  assert.deepEqual(selectRecords(records, { sort: 'code' }).map(r => r.code), ['2330', '2408', '3260']);
});
test('keeps published and self-reported counters separate', () => {
  assert.deepEqual(summarize(records), { total: 3, reported: 2, self_reported: 1, sii: 2, otc: 1, rotc: 0 });
});
test('exports only the supplied selection, quotes commas and neutralizes spreadsheet formulas', () => {
  const csv = toCsv([{ ...records[0], title: '=HYPERLINK("bad"),x' }]);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes("'=HYPERLINK"));
  assert.ok(!csv.includes('南亞科'));
  assert.ok(csv.includes('""bad""'));
});

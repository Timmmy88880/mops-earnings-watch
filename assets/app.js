import { selectRecords, summarize, toCsv } from './core.js';

const $ = id => document.getElementById(id);
const markets = { sii: '上市', otc: '上櫃', rotc: '興櫃', pub: '公開發行' };
const filters = { query: '', status: '', market: '', month: '', sort: 'newest' };
const PAGE_SIZE = 20;
let dataset, page = 1, selection = [];
const text = (id, value) => { $(id).textContent = value; };
const element = (tag, className, content) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
};
const formatTime = value => new Intl.DateTimeFormat('zh-TW', {
  timeZone: 'Asia/Taipei', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
}).format(new Date(value));
const taipeiDate = value => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Taipei', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date(value));
function officialLink(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && (parsed.hostname === 'mopsov.twse.com.tw' || parsed.hostname === 'mops.twse.com.tw');
  } catch { return false; }
}

function showSummary() {
  const { records, meta } = dataset;
  const counts = summarize(records);
  text('period', `${meta.year} · 第${['', '一', '二', '三', '四'][meta.quarter]}季`);
  text('metric-reported', counts.reported);
  text('metric-self', counts.self_reported);
  text('metric-total', counts.total);
  text('list-total', counts.total);
  text('tab-all', counts.total);
  text('tab-reported', counts.reported);
  text('tab-self', counts.self_reported);
  text('metric-market-note', `上市 ${counts.sii} · 上櫃 ${counts.otc} · 興櫃 ${counts.rotc}`);
  text('checked-at', `資料核對 ${formatTime(meta.checked_at)}`);
  const checkedDay = taipeiDate(meta.checked_at);
  const first = new Date(`${checkedDay}T12:00:00+08:00`);
  first.setUTCDate(first.getUTCDate() - 6);
  const firstDay = taipeiDate(first);
  text('metric-week', records.filter(r => r.date >= firstDay && r.date <= checkedDay).length);
  text('metric-week-note', `${firstDay.slice(5).replace('-', '/')} – ${checkedDay.slice(5).replace('-', '/')} 公告公司數`);
  if (/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(meta.repository || '')) {
    $('github-link').href = `https://github.com/${meta.repository}`;
    $('workflow-link').href = `https://github.com/${meta.repository}/actions`;
  }
  if (Date.now() - new Date(meta.checked_at).getTime() > 8 * 86400000) {
    const alert = $('data-alert');
    alert.replaceChildren(element('span', '', `上次成功核對為 ${formatTime(meta.checked_at)}，資料尚待更新。`));
    const link = element('a', '', '查看更新紀錄 ↗');
    link.href = $('workflow-link').href; link.target = '_blank'; link.rel = 'noopener noreferrer';
    alert.append(link); alert.hidden = false;
  }
  const months = [...new Set(records.map(r => r.date.slice(0, 7)))].sort().reverse();
  for (const month of months) {
    const option = element('option', '', `${Number(month.slice(5))} 月`);
    option.value = month; $('month').append(option);
  }
  renderChart(checkedDay);
}

function renderChart(checkedDay) {
  const last = new Date(`${checkedDay}T12:00:00+08:00`);
  const days = [];
  for (let offset = 13; offset >= 0; offset--) {
    const date = new Date(last); date.setUTCDate(date.getUTCDate() - offset);
    const day = taipeiDate(date);
    const matching = dataset.records.filter(r => r.date === day);
    days.push({ day, reported: matching.filter(r => r.status === 'reported').length,
      self: matching.filter(r => r.status === 'self_reported').length });
  }
  const maximum = Math.max(1, ...days.map(d => d.reported + d.self));
  const chart = $('activity-chart'); chart.replaceChildren();
  chart.setAttribute('aria-label', '近兩週每日公告：' + days.map(d => `${d.day.slice(5)} ${d.reported + d.self}家`).join('，'));
  for (const day of days) {
    const total = day.reported + day.self;
    const column = element('div', 'chart-column');
    column.title = `${day.day}：財報 ${day.reported} 家、自結 ${day.self} 家`;
    const count = element('span', 'chart-count', total || '');
    const bar = element('div', 'chart-bar'); bar.style.height = `${Math.max(2, total / maximum * 72)}px`;
    if (total) {
      for (const [status, value] of [['reported', day.reported], ['self', day.self]]) {
        const segment = element('div', `chart-segment ${status}`);
        segment.style.height = `${value / total * 100}%`; bar.append(segment);
      }
    }
    column.append(count, bar, element('span', 'chart-label', `${Number(day.day.slice(5, 7))}/${Number(day.day.slice(8))}`));
    chart.append(column);
  }
}

function renderRow(record) {
  const tr = element('tr');
  const company = element('td');
  const identity = element('div', 'company-cell');
  const info = element('div', 'company-info');
  info.append(element('div', 'company-name', record.name), element('span', 'company-code', record.code));
  identity.append(element('span', 'company-avatar', record.name.charAt(0)), info); company.append(identity);
  const status = element('td');
  status.append(element('span', `status-badge ${record.status}`, record.status === 'reported' ? '財報已公布' : '自結數'));
  if (record.status === 'self_reported' && record.cumulative) status.append(element('small', 'cumulative-note', '含前三季累計'));
  const date = element('td', 'date-cell');
  const time = element('time', '', record.date.replaceAll('-', '/')); time.dateTime = record.date;
  date.append(time, element('span', 'announcement-time', record.time.slice(0, 5)));
  const market = element('td', 'market-cell', markets[record.market] || '—');
  const title = element('td');
  const titleText = element('span', 'announcement-title', record.title); titleText.title = record.title; title.append(titleText);
  const source = element('td', 'source-cell');
  if (officialLink(record.url)) {
    const link = element('a', 'source-link', '↗');
    link.href = record.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.setAttribute('aria-label', `查看${record.name}（${record.code}）官方公告（另開視窗）`);
    source.append(link);
  }
  tr.append(company, status, date, market, title, source);
  return tr;
}

function render(resetPage = false) {
  if (!dataset) return;
  if (resetPage) page = 1;
  selection = selectRecords(dataset.records, filters);
  const pages = Math.max(1, Math.ceil(selection.length / PAGE_SIZE));
  page = Math.min(page, pages);
  const start = (page - 1) * PAGE_SIZE;
  $('records').replaceChildren(...selection.slice(start, start + PAGE_SIZE).map(renderRow));
  $('empty-state').hidden = selection.length > 0;
  $('previous').disabled = page <= 1; $('next').disabled = page >= pages;
  $('export').disabled = selection.length === 0;
  text('result-count', `共 ${selection.length} 家符合條件`);
  text('page-info', selection.length ? `顯示 ${start + 1}–${Math.min(start + PAGE_SIZE, selection.length)} 家，共 ${selection.length} 家` : '沒有符合條件的公司');
  text('page-current', `${page} / ${pages}`);
  for (const button of document.querySelectorAll('[data-status]')) {
    const active = button.dataset.status === filters.status;
    button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
  }
}

for (const button of document.querySelectorAll('[data-status]')) button.addEventListener('click', () => {
  filters.status = button.dataset.status; render(true);
});
$('search').addEventListener('input', event => { filters.query = event.target.value; render(true); });
for (const id of ['market', 'month', 'sort']) $(id).addEventListener('change', event => {
  filters[id] = event.target.value; render(true);
});
$('previous').addEventListener('click', () => { page--; render(); });
$('next').addEventListener('click', () => { page++; render(); });
$('reset').addEventListener('click', () => {
  Object.assign(filters, { query: '', status: '', market: '', month: '', sort: 'newest' });
  $('search').value = ''; $('market').value = ''; $('month').value = ''; $('sort').value = 'newest'; render(true);
});
$('export').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([toCsv(selection)], { type: 'text/csv;charset=utf-8' }));
  const link = element('a'); link.href = url; link.download = `${dataset.meta.year}-Q${dataset.meta.quarter}-財報名單.csv`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

async function load() {
  try {
    const response = await fetch('./data/2026-q3.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!data.meta?.checked_at || !Array.isArray(data.records)) throw new Error('Invalid data');
    dataset = data; showSummary(); render();
  } catch (error) {
    console.error('Could not load disclosure data', error);
    text('checked-at', '資料暫時無法載入');
    text('result-count', '無法取得公告資料');
    const cell = element('td', 'loading-state', '暫時無法載入名單，請重新整理頁面後再試。');
    cell.colSpan = 6; const row = element('tr'); row.append(cell); $('records').replaceChildren(row);
  }
}
load();

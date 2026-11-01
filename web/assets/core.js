export function selectRecords(records, filters = {}) {
  const query = (filters.query || '').trim().toLocaleLowerCase('zh-TW');
  return records.filter(record =>
    (!query || `${record.code} ${record.name}`.toLocaleLowerCase('zh-TW').includes(query)) &&
    (!filters.market || record.market === filters.market) &&
    (!filters.status || record.status === filters.status) &&
    (!filters.month || record.date.startsWith(filters.month))
  ).sort((a, b) => {
    if (filters.sort === 'code') return a.code.localeCompare(b.code);
    const dateOrder = `${a.date} ${a.time || ''}`.localeCompare(`${b.date} ${b.time || ''}`);
    return (filters.sort === 'oldest' ? dateOrder : -dateOrder) || a.code.localeCompare(b.code);
  });
}

export function summarize(records) {
  const counts = { total: records.length, reported: 0, self_reported: 0, sii: 0, otc: 0, rotc: 0 };
  for (const record of records) {
    if (record.status in counts) counts[record.status]++;
    if (record.market in counts) counts[record.market]++;
  }
  return counts;
}

export function toCsv(records) {
  const field = value => {
    let text = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  const markets = { sii: '上市', otc: '上櫃', rotc: '興櫃', pub: '公開發行' };
  const rows = [['代號', '公司', '市場', '狀態', '公告日期', '公告主旨', '官方公告']];
  for (const r of records) rows.push([r.code, r.name, markets[r.market], r.status === 'reported' ? '財報已公布' : '自結數', r.date, r.title, r.url]);
  return '\uFEFF' + rows.map(row => row.map(field).join(',')).join('\r\n');
}

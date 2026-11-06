export function normalizeApplication(row) {
  let history = row.status_history;
  if (typeof history === 'string') {
    try { history = JSON.parse(history); } catch { history = null; }
  }
  history = Array.isArray(history) ? history.filter(event => event && typeof event.status === 'string') : [];
  if (!history.length) history = [{status: row.status || 'Applied', at: null}];
  return {...row, status_history: history};
}

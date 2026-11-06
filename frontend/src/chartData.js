const key = date => date.toLocaleDateString('en-CA');
export function applicationStatistics(rows, interval, now = new Date()) {
  const anchor = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (interval === 'Weekly') anchor.setDate(anchor.getDate() - (anchor.getDay() + 6) % 7);
  if (interval === 'Monthly') anchor.setDate(1);
  const count = interval === 'Daily' ? 30 : 12;
  return Array.from({length: count}, (_, index) => {
    const start = new Date(anchor), end = new Date(anchor);
    const offset = index - count + 1;
    if (interval === 'Monthly') {
      start.setMonth(start.getMonth() + offset);
      end.setMonth(end.getMonth() + offset + 1);
    } else {
      const days = interval === 'Weekly' ? 7 : 1;
      start.setDate(start.getDate() + offset * days);
      end.setDate(end.getDate() + (offset + 1) * days);
    }
    const entries = rows.filter(row => row.applied_date >= key(start) && row.applied_date < key(end));
    const label = start.toLocaleDateString('en-US', interval === 'Monthly' ? {month:'short',year:'numeric'} : {month:'short',day:'numeric'});
    return {date: label, fullDate: interval === 'Weekly' ? `Week of ${start.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}` : start.toLocaleDateString('en-US', interval === 'Monthly' ? {month:'long',year:'numeric'} : {month:'short',day:'numeric',year:'numeric'}), Applications: entries.length, Interviewing: entries.filter(row => row.status === 'Interviewing').length};
  });
}

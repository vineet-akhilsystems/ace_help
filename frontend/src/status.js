export const STATUS = {
  filled:    {label:'Filled',          hint:'9 hours or more saved'},
  partial:   {label:'Needs attention', hint:'Under 9 hours saved in ACE'},
  missing:   {label:'Not filled',      hint:'0 hours in ACE (unsaved drafts count as not filled)'},
  failed:    {label:'Could not fill',  hint:'The app was stopped by an error'},
  unchecked: {label:'Not checked',     hint:'Run Check ACE'},
  leave:     {label:'Leave',           hint:'Marked by you'},
};

export const PENDING = ['missing', 'partial', 'failed'];

export function pendingDays(days, limit = 5) {
  return days.filter(d => PENDING.includes(d.status)).sort((a, b) => a.date.localeCompare(b.date)).slice(0, limit);
}

export function progress(status) {
  const due = status.workingDays - status.counts.leave;
  return due > 0 ? Math.round(100 * status.counts.filled / due) : 0;
}

export function shiftMonth(month, delta) {
  const [y, m] = month.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

// Leading blanks so the 1st lands under its weekday in a Monday-first grid.
export function leadingBlanks(month) {
  const [y, m] = month.split('-').map(Number);
  return (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7;
}

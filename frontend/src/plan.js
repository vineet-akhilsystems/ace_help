export function minute(time) {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return NaN;
  const [h,m] = time.split(':').map(Number); return h * 60 + m;
}
export function total(tasks) {
  const sum = tasks.reduce((n,t) => n + minute(t.end) - minute(t.start), 0);
  if (!Number.isFinite(sum) || sum < 0) return '00:00';
  return `${String(Math.floor(sum/60)).padStart(2,'0')}:${String(sum%60).padStart(2,'0')}`;
}
export function adjustLongDay(plan) {
  const tasks = plan.tasks || [];
  if (!tasks.length) return plan;
  const start = minute(tasks[0].start);
  const end = minute(tasks.at(-1).end);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end - start < 570) return plan;
  if (tasks.some((task, i) => i && task.start !== tasks[i-1].end)) return plan;
  const last = tasks.at(-1);
  const adjustedEnd = start + 555;
  if (minute(last.start) >= adjustedEnd) return plan;
  const updated = tasks.map((task, i) => i === tasks.length - 1
    ? {...task, end:`${String(Math.floor(adjustedEnd/60)).padStart(2,'0')}:${String(adjustedEnd%60).padStart(2,'0')}`}
    : task);
  return {...plan, tasks:updated, totalHours:total(updated)};
}
export function validation(plans) {
  const issues = [];
  for (const p of plans) {
    const fail = msg => issues.push(`${p.date}: ${msg}`);
    if (!p.tasks.length) { fail('Add at least one task.'); continue; }
    let end = minute(p.tasks[0].start);
    if (!(end >= 585 && end <= 600)) fail('Start between 09:45 and 10:00.');
    for (const t of p.tasks) {
      if (!t.description.trim() || t.description.length > 500) fail('Each description needs 1–500 characters.');
      if (t.ticket && !t.description.startsWith(`[${t.ticket}] `)) fail('The selected ticket must prefix its description.');
      if (minute(t.start) !== end || !(minute(t.end) > end)) fail('Times must be contiguous and end after they start.');
      end = minute(t.end);
    }
    if (!(end - minute(p.tasks[0].start) >= 540 && end - minute(p.tasks[0].start) < 570))
      fail('Total must be at least 9 hours and below 9 hours 30 minutes.');
  }
  return [...new Set(issues)];
}
export function tagTask(task, ticket) {
  const text = task.description.replace(/^\[ASPL-\d{5,8}\]\s*/, '');
  const prefix = ticket ? `[${ticket}] ` : '';
  return {...task, ticket: ticket || null, matchReason: ticket ? 'Selected by you.' : null,
    description: prefix + text.slice(0, 500 - prefix.length)};
}
// Condenses selected activity into one line per day and project, so "select all" fits the 20,000-character notes.
export function ideaNotes(items, manual = '') {
  const groups = new Map();
  for (const item of items) {
    const key = `${item.date} · ${item.repo || 'other work'}`;
    const kinds = groups.get(key) || new Map();
    const name = item.kind === 'commit' ? `"${item.title}"` : item.title.replace(/^[^:]+:\s*/, '');
    kinds.set(item.kind, [...(kinds.get(item.kind) || []), name]);
    groups.set(key, kinds);
  }
  const lines = [...groups].map(([key, kinds]) => key + ': ' + [...kinds].map(([kind, names]) =>
    `${kind}: ${[...new Set(names)].slice(0, 12).join(', ')}${names.length > 12 ? ` (+${names.length - 12} more)` : ''}`).join('; ') + '.');
  const head = 'Work I did that has no ACE ticket yet. Create one ticket per distinct piece of work and combine items that belong to the same work.';
  return [head, ...lines, ...(manual.trim() ? [manual.trim()] : [])].join('\n').slice(0, 20000);
}
// Drafts from your own past work ask "Have you completed this?"; the answer sets the ACE status.
// (The Target Date stays in the future: ACE rejects one before now.)
export function markDone(task, done, statuses) {
  return {...task, done, status: snapOption(done ? 'Completed' : 'Open', statuses)};
}
export function completionIssues(tasks, numbers = tasks.map((_, i) => i + 1)) {
  return tasks.map((t, i) => t.askDone && t.done == null ? `Task ${numbers[i]}: answer "Have you completed this?"` : null).filter(Boolean);
}
// "Task 1: choose X." … "Task 16: choose X." → "Tasks 1–16: choose X." so a long batch stays readable.
export function groupIssues(issues) {
  const groups = new Map(), other = [];
  for (const issue of issues) {
    const m = /^Task (\d+): (.*)$/.exec(issue);
    if (m) groups.set(m[2], [...(groups.get(m[2]) || []), Number(m[1])]);
    else other.push(issue);
  }
  const ranges = ns => ns.sort((a, b) => a - b).reduce((out, n) => {
    const last = out.at(-1);
    if (last && n === last[1] + 1) last[1] = n; else out.push([n, n]);
    return out;
  }, []).map(([a, b]) => a === b ? `${a}` : `${a}–${b}`).join(', ');
  return [...other, ...[...groups].map(([msg, ns]) => `${ns.length > 1 ? 'Tasks' : 'Task'} ${ranges(ns)}: ${msg}`)];
}
// Review-only fields that never go to ACE.
export function aceTask({warnings, link, askDone, done, pick, existingTicket, outcome, linkedTicket, workDate, ...task}) {
  return {...task, effortDays:Number(task.effortDays), warnings:[]};
}
// Timesheet rows that still need an ACE ticket, grouped by day for /tasks/from-timesheet.
export function ticketlessRows(plans) {
  return plans.map(p => ({date:p.date, tasks:p.tasks.map((t, index) => ({index, description:t.description,
    minutes:minute(t.end) - minute(t.start)})).filter(t => !p.tasks[t.index].ticket && t.minutes > 0)}))
    .filter(d => d.tasks.length);
}
// Tags each linked row with the ticket the user saved for it; returns the plans and how many rows changed.
export function applyTicketLinks(plans, links) {
  let applied = 0;
  const next = plans.map(p => {
    const mine = links.filter(l => l.date === p.date && l.ticket);
    if (!mine.length) return p;
    const tasks = p.tasks.map((t, i) => {
      const link = mine.find(l => l.index === i);
      if (!link || t.ticket) return t;
      applied++;
      return {...tagTask(t, link.ticket), matchReason:'New ticket you created for this work.'};
    });
    return {...p, tasks};
  });
  return {plans:next, applied};
}

export const TASK_REQUIRED = {taskType:'Task Type', priority:'Priority', client:'Client Name', module:'Module', status:'Task Status'};
export const TASK_MAX = 30;
const optionKey = s => String(s ?? '').replace(/\s+/g, ' ').trim().toLowerCase();
// ACE option texts carry stray spaces ("Cloud LIS "); match loosely, keep ACE's exact text.
export function snapOption(value, choices) {
  if (!value || !choices) return value;
  if (choices.includes(value)) return value;
  return choices.find(c => optionKey(c) === optionKey(value)) ?? value;
}
export function taskIssues(tasks, options, numbers = tasks.map((_, i) => i + 1), now = new Date()) {
  const issues = [];
  if (tasks.length > TASK_MAX) issues.push(`ACE fills at most ${TASK_MAX} tasks at a time; remove ${tasks.length - TASK_MAX}.`);
  tasks.forEach((t, i) => {
    const fail = msg => issues.push(`Task ${numbers[i]}: ${msg}`);
    for (const [field, label] of Object.entries(TASK_REQUIRED)) {
      if (!t[field]) fail(`choose ${label}.`);
      else if (options && !options[field]?.includes(snapOption(t[field], options[field]))) fail(`${label} "${t[field]}" is not an ACE option.`);
    }
    if (t.frdNature && options && !options.frdNature?.includes(snapOption(t.frdNature, options.frdNature))) fail('FRD Nature is not an ACE option.');
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t.targetDate || '')) fail('set Target Date.');
    else if (new Date(t.targetDate) < now) fail('Target Date must be later than now (ACE replaces a past date).');
    if (!(Number(t.effortDays) > 0 && Number(t.effortDays) <= 365)) fail('Effort in Days must be above 0.');
    for (const [field, label] of [['keyword','Keyword'],['description','Description'],['clientRemarks','Client Remarks'],['employeeRemarks','Employee Remarks']])
      if (!t[field]?.trim()) fail(`${label} is required.`);
    if ((t.keyword || '').trim().length > 25) fail('Keyword must be 25 characters or fewer (ACE cuts the rest).');
  });
  if (!tasks.length) issues.push('Add at least one task.');
  return issues;
}

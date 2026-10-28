// Helpers for drafting a day with the user's own coding agent.
export function agentPayload({date, toDate, range, notes, perDayMode, perDay, agent}) {
  return {fromDate:date, toDate:range ? toDate : null, agent,
    notes:perDayMode && range ? '' : notes, perDay:perDayMode && range ? perDay : {}};
}

// Drafts the agent submitted (for example from chat) that this browser has not shown yet.
export function newDrafts(list, seen) {
  return list.filter(d => !seen[d.date] || d.createdAt > seen[d.date]);
}

// Never overwrite a plan the user has edited; offer the incoming draft instead.
export function mergeIncomingDraft(plans, draft, edited) {
  const index = plans.findIndex(p => p.date === draft.date);
  if (index >= 0 && edited)
    return {plans, notice:`A new draft from your agent for ${draft.date} is ready. Load it?`};
  const next = index >= 0 ? plans.map((p, i) => i === index ? draft : p) : [...plans, draft];
  return {plans:next.sort((a, b) => a.date.localeCompare(b.date)), notice:null};
}

// Per-browser conveniences only; storage can be unavailable, so never let it break the page.
export function readStored(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch (_) {
    return fallback;
  }
}
export function writeStored(key, value) {
  try {localStorage.setItem(key, JSON.stringify(value));} catch (_) { /* ignore */ }
}

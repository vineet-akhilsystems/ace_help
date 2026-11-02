import React, {useEffect, useState} from 'react';
import {ACE_FIELDS, ACE_MODULES, ACE_STATUSES, EMPLOYEES, SKIP, distinctValues, statusValues, draftIssues, fieldValue, isOpenRow,
  mappingRows, matchEmployee, matchModule, missingColumns, resolveModule, resolvePerson, sheetDrafts, taskDraft, withDefaults} from './assign';
import {readStored} from './agent';
import {api} from './api';

const SETTINGS_KEY = 'ace.assign.settings';
const SOURCES = {fixed: 'Same value every time', column: 'From a sheet column', template: 'Combine sheet columns'};
const today = () => new Date().toLocaleDateString('en-CA');
const HOW = {exact: 'Exact match', auto: 'Matched from', saved: 'Your setting for', default: 'No one in the sheet'};
// The choices for a blank Module / Assign To / Status cell; "skip" (no ticket) is the default for all three.
const EMPTY_RULES = [
  {field: 'module', label: 'Module', choices: {skip: 'No ticket for that row', pick: 'Make the ticket, I pick the module'}},
  {field: 'assignTo', label: 'Assign To', choices: {skip: 'No ticket for that row', fallback: 'Give it to'}},
  {field: 'status', label: 'Status', choices: {skip: 'No ticket for that row', table: 'Use the Statuses table’s (empty) row'}},
];
const when = iso => iso ? new Date(iso).toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '—';

function ColumnSelect({columns, value, onChange, empty}) {
  return <select value={value || ''} onChange={e => onChange(e.target.value)}>
    {empty && <option value="">{empty}</option>}
    {value && !columns.includes(value) && <option value={value}>{value} (not in sheet)</option>}
    {columns.map(c => <option key={c} value={c}>{c}</option>)}
  </select>;
}

function FieldRule({field, config, columns, onChange}) {
  const sources = field === 'targetDate' ? {days: 'Sheet date, else today + days', fixed: SOURCES.fixed} : SOURCES;
  return <div className="map-rule">
    <select aria-label={`${field} source`} value={config.source} onChange={e => onChange({source: e.target.value,
      value: e.target.value === 'column' ? columns[0] : e.target.value === 'days' ? 7 : e.target.value === 'template' ? `{${columns[0]}}` : ''})}>
      {Object.entries(sources).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
    </select>
    {config.source === 'fixed' && <input aria-label={`${field} value`} value={config.value} onChange={e => onChange({...config, value: e.target.value})}/>}
    {config.source === 'column' && <ColumnSelect columns={columns} value={config.value} onChange={v => onChange({...config, value: v})}/>}
    {config.source === 'days' && <span className="map-inline">
      <ColumnSelect columns={columns} value={config.column} empty="No sheet date" onChange={v => onChange({...config, column: v})}/>
      <span>else today +</span>
      <input type="number" min="0" aria-label="Days from today" value={config.value} onChange={e => onChange({...config, value: e.target.value})}/>
      <span>days</span>
    </span>}
    {config.source === 'template' && <span className="map-template">
      <textarea aria-label={`${field} template`} value={config.value} onChange={e => onChange({...config, value: e.target.value})}/>
      <select value="" aria-label="Insert a column" onChange={e => e.target.value && onChange({...config, value: `${config.value}{${e.target.value}}`})}>
        <option value="">+ Insert column…</option>
        {columns.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    </span>}
  </div>;
}

// One mapping per sheet value: values found in the sheet, saved ones it no longer uses, and values added by hand.
// none: what an unmapped value means when that is a normal choice (statuses: no ticket), instead of "Pick one…".
function MappingTable({target, rows, saved, keyOf, autoOf, choices, skip, none, countLabel = 'Open rows', onChange}) {
  const [name, setName] = useState('');
  const [pick, setPick] = useState('');
  const put = (key, value) => {
    const next = {...saved};
    if (value === '') delete next[key]; else next[key] = value;
    onChange(next);
  };
  const options = current => <>
    {current && current !== SKIP && !choices.includes(current) && <option value={current}>{current} (not in ACE)</option>}
    {choices.map(c => <option key={c} value={c}>{c}</option>)}
    {skip && <option value={SKIP}>Skip these rows</option>}
  </>;
  const add = () => { put(keyOf(name.trim()), pick); setName(''); setPick(''); };
  return <div className="map-table">
    <div className="map-head"><span>In the sheet</span><span>{target}</span><span>{countLabel}</span></div>
    {rows.map(({value, count, inSheet}) => {
      const key = keyOf(value), current = saved[key], auto = autoOf(value);
      const bad = current ? current !== SKIP && !choices.includes(current) : !auto && !none;
      return <div className="map-row" key={key}>
        <b>{value || '(empty)'}</b>
        <select aria-label={`${target} for ${value}`} className={bad ? 'bad' : ''} value={key in saved ? current : ''}
          onChange={e => put(key, e.target.value)}>
          <option value="">{auto ? `Automatic: ${auto}` : none || 'Pick one…'}</option>
          {options(current)}
        </select>
        <span className="map-example">{inSheet ? count
          : <>Not in the sheet now <button className="ghost small" onClick={() => put(key, '')}>Remove</button></>}</span>
      </div>;
    })}
    <div className="map-row">
      <input aria-label={`Add a sheet value for ${target}`} placeholder="Add a sheet value…" value={name} onChange={e => setName(e.target.value)}/>
      <select aria-label={`${target} for the added value`} value={pick} onChange={e => setPick(e.target.value)}>
        <option value="">Pick one…</option>{options('')}
      </select>
      <span><button className="ghost small" disabled={!name.trim() || !pick || keyOf(name.trim()) in saved} onClick={add}>Add</button></span>
    </div>
  </div>;
}

export function TicketAssign({modeSwitch}) {
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  // The sheet as the backend read it, and the ACE account tickets are created with.
  const [source, setSource] = useState({columns: [], rows: [], path: '', account: '', ready: false, sheetUrl: ''});
  const [link, setLink] = useState(null);  // the Sheet link being edited; null = showing the one saved in .env
  const saveLink = async () => {
    setBusy('Saving the link…'); setError('');
    try {
      const {sheetUrl} = await api('/assign/sheet-url', {url: link.trim()});
      setSource(s => ({...s, sheetUrl})); setLink(null);
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };
  // Settings live in the app, because the 30-minute run uses them with no page open. null until loaded.
  const [saved, setSaved] = useState(null);
  const [settings, setSettings] = useState(() => withDefaults({}));
  const [auto, setAuto] = useState(null);
  const [sheet, setSheet] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [confirmed, setConfirmed] = useState(false);
  const [log, setLog] = useState([]);
  // ACE's own Module and Assign To lists, the same ones Create tasks uses; the built-in lists are only stand-ins.
  const [ace, setAce] = useState({modules: ACE_MODULES, employees: EMPLOYEES, statuses: ACE_STATUSES, loadedAt: null, error: ''});
  const loadAce = result => setAce({modules: result.options.module, loadedAt: result.loadedAt, error: '',
    employees: result.employees?.length ? result.employees : EMPLOYEES,
    statuses: result.options.status?.length ? result.options.status : ACE_STATUSES});
  const loadSheet = async next => {
    const fresh = await api('/assign/sheet', {source: next.source, sheetTab: next.sheetTab});
    setSource(fresh);
    return fresh;
  };
  useEffect(() => {
    api('/task-options').then(loadAce).catch(e => setAce(a => ({...a, error: e.message})));
    api('/assign/auto').then(setAuto).catch(() => {});
    api('/assign/settings').then(async body => {
      // Settings kept in this browser before they moved into the app are offered once, as unsaved changes.
      const local = body.saved ? null : readStored(SETTINGS_KEY, null);
      const loaded = withDefaults(body.settings);
      setSaved(loaded);
      setSettings(local ? withDefaults({...body.settings, ...local, source: body.settings.source}) : loaded);
      setSource(s => ({...s, account: body.account, ready: body.ready, sheetUrl: body.sheetUrl, path: body.path}));
      setBusy('Reading the sheet…');
      try { await loadSheet(loaded); } finally { setBusy(''); }
    }).catch(e => setError(e.message));
    // The 30-minute run happens in the app; keep its status fresh while this tab is open.
    const timer = setInterval(() => api('/assign/auto').then(setAuto).catch(() => {}), 30000);
    return () => clearInterval(timer);
  }, []);
  const refreshAce = async () => {
    setBusy('Reading modules from ACE…');
    try { loadAce(await api('/task-options/refresh', {})); }
    catch (e) { setAce(a => ({...a, error: e.message})); }
    finally { setBusy(''); }
  };
  const {modules, employees} = ace;

  const {columns, rows} = source;
  const dirty = !!saved && JSON.stringify(settings) !== JSON.stringify(saved);
  const missing = columns.length ? missingColumns(settings, columns) : [];
  const example = rows.find(r => isOpenRow(r, settings));
  const set = patch => setSettings(s => ({...s, ...patch}));
  const setField = (field, config) => setSettings(s => ({...s, fields: {...s.fields, [field]: config}}));
  const store = async next => {
    const body = await api('/assign/settings', next);
    const normal = withDefaults(body.settings);
    setSaved(normal); setSettings(normal);
    return normal;
  };
  // Saves one change on top of the saved settings, leaving other unsaved edits as they are.
  const keep = patch => {
    setSettings(s => ({...s, ...patch}));
    api('/assign/settings', {...saved, ...patch}).then(body => setSaved(withDefaults(body.settings))).catch(e => setError(e.message));
  };
  const saveSettings = async () => {
    setBusy('Saving settings…'); setError('');
    try { await store(settings); } catch (e) { setError(e.message); } finally { setBusy(''); }
  };

  const read = async () => {
    setBusy('Reading the sheet…'); setLog([]); setConfirmed(false); setError('');
    try {
      const fresh = await loadSheet(settings);
      const result = sheetDrafts(fresh.rows, settings, today(), modules, employees);
      setSheet({...result, total: fresh.rows.length, checkedAt: new Date().toLocaleTimeString('en-IN', {hour: '2-digit', minute: '2-digit'})});
      setDrafts(result.drafts);
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };
  const update = (i, patch) => setDrafts(ds => ds.map((d, j) => j === i ? {...d, ...patch} : d));
  // A pick on a ticket is also saved as a setting, so the next run (and the 30-minute run) uses it.
  const pickPerson = (i, name) => {
    const d = drafts[i];
    if (d.sheetName) keep({people: {...settings.people, [d.sheetName.toLowerCase()]: name}});
    update(i, {assignee: name, warnings: d.warnings.filter(w => !w.includes('Pick who'))});
  };
  // Saved (or saved but unconfirmed) tickets are final; a filled one can still be created, reusing its open ACE tab.
  const done = d => ['saved', 'unconfirmed'].includes(d.outcome?.status);
  const chosen = drafts.filter(d => d.pick && !done(d));
  const issues = chosen.flatMap(d => draftIssues(d).map(f => `Row ${d.row}: ${f} is missing.`));

  // Fill only opens one ACE tab per ticket and never saves; Create also saves and writes the number to the sheet.
  const send = async save => {
    const picked = drafts.filter(d => d.pick && !done(d));
    setBusy(save ? 'Creating tickets in ACE…' : 'Filling ACE…'); setError('');
    try {
      const result = await api('/assign/create', {save, settings,
        tickets: picked.map(d => ({row: d.row, draft: taskDraft(d)}))});
      const byRow = Object.fromEntries(result.tasks.map(r => [picked[r.index - 1].row, r]));
      setDrafts(ds => ds.map(d => byRow[d.row] ? {...d, outcome: byRow[d.row]} : d));
      setLog(result.tasks.map(r => `Row ${picked[r.index - 1].row} → ${picked[r.index - 1].assignee}: ${r.message}${r.sheet ? ' ' + r.sheet : ''}`));
      if (save) await loadSheet(settings);
    } catch (e) { setError(e.message); }
    finally { setBusy(''); setConfirmed(false); }
  };

  // The automatic run always uses the saved settings, so unsaved changes are saved first.
  const switchAuto = async on => {
    setBusy(on ? 'Switching on…' : 'Switching off…'); setError('');
    try {
      if (on && dirty) await store(settings);
      setAuto(await api('/assign/auto', {on}));
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };
  // Run now goes on in the app; this only starts it, then follows it closely until it ends.
  const [count, setCount] = useState('');  // how many tickets Run now creates; empty = every waiting row
  const runNow = async () => {
    setBusy('Starting…'); setError('');
    try {
      if (dirty) await store(settings);
      setAuto((await api('/assign/run-now', {count: Number(count) > 0 ? Math.floor(Number(count)) : null})).auto);
    } catch (e) { setError(e.message); }
    finally { setBusy(''); }
  };
  const stopRun = () => api('/assign/stop', {}).then(r => setAuto(r.auto)).catch(e => setError(e.message));
  const running = !!auto?.running;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => api('/assign/auto').then(next => {
      setAuto(next);
      if (!next.running) loadSheet(settings).catch(() => {});
    }).catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [running]);

  const exampleOf = field => {
    if (!example) return '—';
    const raw = fieldValue(settings.fields[field], example, today());
    if (field === 'module') { const m = resolveModule(raw, settings, modules).module; return `${raw} → ${m === SKIP ? 'skipped' : m || 'no match'}`; }
    if (field === 'assignTo') return `${raw || '(empty)'} → ${resolvePerson(raw, settings, employees).name || 'pick'}`;
    return raw || '(empty)';
  };
  const moduleValues = distinctValues(rows, settings, 'module');
  const personValues = distinctValues(rows, settings, 'assignTo').filter(p => p.value);
  const live = settings.source !== 'test';
  // What Read sheet would make now; the waiting count and the empty-cell rule counts come from it.
  const preview = sheetDrafts(rows, settings, today(), modules, employees);
  const waiting = preview.drafts.length;
  const emptyColumn = field => {
    if (field === 'status') return `column ${settings.statusColumn}`;
    const config = settings.fields[field];
    return config.source === 'column' ? `column ${config.value}` : 'not from a column';
  };

  return <div className="app">
    <header><div className="brand-group">
      <span className="brand"><span className="logo">a.</span> ACE <span className="brand-sub">/ ticket assignment</span></span>
      {modeSwitch}
    </div></header>
    <main className="dash">
      <section className="panel dash-summary">
        <h2>Assign tickets from the sheet</h2>
        <p>Reads the sheet, keeps rows whose {settings.statusColumn} is picked under Settings → Statuses
          ({Object.entries(settings.statuses).filter(([, v]) => v !== SKIP).map(([k, v]) => `${k} → ${v}`).join(', ') || 'none yet'}) and
          whose {settings.ticketColumn} is empty, and creates one ACE ticket per row using the settings below. The only thing ever written back is the new ASPL number in {settings.ticketColumn}.</p>
        <div className="idea-controls">
          <span className="pill">{source.account ? `ACE account: ${source.account}` : 'ACE account not set'}</span>
          <span className="pill">{live ? 'Live OneDrive sheet' : 'Test copy'}</span>
          <button className="primary" disabled={!!busy || !saved || missing.length > 0} onClick={read}>
            {busy === 'Reading the sheet…' ? busy : 'Read sheet'}
          </button>
        </div>
        {source.account && !source.ready && <p className="error">The ACE password for {source.account} is missing in .env. Add it and restart the app.</p>}
        {saved && !source.account && <p className="error">No ACE account is set for ticket assignment in .env (ACE_ASSIGN_ACCOUNT and its _USERNAME / _PASSWORD). Add it and restart the app.</p>}
        <small>Reads {live ? (source.sheetUrl ? <a href={source.sheetUrl} target="_blank" rel="noreferrer">the OneDrive sheet</a> : 'the OneDrive sheet (no link yet: add it under Settings → Sheet link)')
          : <>the test copy {source.path && <code>{source.path}</code>}</>}. Change this under Settings → Sheet.{dirty && ' · Settings changed but not saved.'}</small>
        {error && <div role="alert" className="error">{error}</div>}
      </section>

      {auto && <section className="panel dash-summary">
        <h2>Automatic run</h2>
        <label className="check auto-switch">
          <input type="checkbox" checked={auto.on} disabled={!!busy || !source.ready} onChange={e => switchAuto(e.target.checked)}/>
          Every {auto.intervalMinutes} minutes, create tickets for new rows and write their numbers into the sheet
        </label>
        <p className="dash-muted">{auto.on
          ? `On since ${when(auto.since)} · next check ${when(auto.nextRun)}. The timer only takes rows added after it was switched on; Run now takes every waiting row.`
          : 'Off. Switching it on leaves the rows already waiting for Run now; only rows added after that are created automatically. It runs while this app is running.'}</p>
        {auto.waitingToWrite > 0 && <p className="warning">{auto.waitingToWrite} ticket {auto.waitingToWrite === 1 ? 'number is' : 'numbers are'} not in the sheet yet. The next run writes {auto.waitingToWrite === 1 ? 'it' : 'them'}; no new ticket is made.</p>}
        {auto.unconfirmed > 0 && <p className="warning">ACE did not confirm {auto.unconfirmed} {auto.unconfirmed === 1 ? 'save' : 'saves'}. Check ACE; those rows are never created again automatically.</p>}
        <div className="idea-controls">
          {running ? <>
            <button className="ghost" disabled={auto.stopping} onClick={stopRun}>{auto.stopping ? 'Stopping after this ticket…' : 'Stop'}</button>
            <small>{auto.running.reason === 'manual' ? 'Run now' : 'Timer run'} going: {auto.running.total
              ? `ticket ${Math.max(auto.running.current, 1)} of ${auto.running.total}` : 'reading the sheet…'} Stop ends it after the ticket
              in progress; numbers of saved tickets are still written to the sheet.</small>
          </> : <>
            <label className="run-count">How many
              <input type="number" min="1" max={waiting || undefined} placeholder="All" value={count} disabled={!!busy}
                aria-label="How many tickets to create" onChange={e => setCount(e.target.value)}/>
              <span>of {waiting} waiting</span>
            </label>
            <button className="ghost" disabled={!!busy || !source.ready} onClick={runNow}>
              {busy === 'Starting…' ? busy : Number(count) > 0 ? `Run now: ${Math.floor(Number(count))}` : 'Run now: all'}
            </button>
            <small>{Number(count) > 0 ? `Creates tickets for the first ${Math.floor(Number(count))}` : 'Creates tickets for every one'} of
              the picked rows without a number, in sheet order, including rows waiting since switch-on, with the saved
              settings. The rest stay for the next Run now. You can stop it while it runs.</small>
          </>}
        </div>
        {auto.runs.length > 0 && <div className="auto-runs">
          {auto.runs.slice(0, 5).map(r => <div className="auto-run" key={r.at}>
            <b>{when(r.at)} · {r.reason === 'manual' ? 'Run now' : 'Timer'}</b>
            {r.error ? <span className="error-text">Stopped: {r.error}</span>
              : <span>{r.rows} rows read · {r.new ?? 0} {r.reason === 'manual' ? 'waiting' : 'new'} · {r.created.length} created · {r.held.length} held{r.failed.length ? ` · ${r.failed.length} failed` : ''}{r.stopped ? ` · stopped, ${r.stopped} not started` : ''}{r.left ? ` · ${r.left} left for the next run` : ''}</span>}
            {r.created.map(c => <small key={'c' + c.row}>Row {c.row} → {c.assignee}: {c.ticket || 'saved, number not found yet'}. {c.sheet}</small>)}
            {r.failed.map(c => <small key={'f' + c.row}>Row {c.row} → {c.assignee}: {c.message}</small>)}
            {r.held.map(h => <small key={'h' + h.row}>Row {h.row} ({h.sheetName || 'no name'}) held: {h.reasons.join('; ')}. Fix it in Settings and it is created on the next run.</small>)}
            {r.written.map(w => <small key={'w' + w}>{w}</small>)}
          </div>)}
        </div>}
      </section>}

      <details className="panel dash-summary map-settings" open>
        <summary><h2>Settings: how the sheet fills ACE</h2></summary>
        {missing.length > 0 && <p className="error" role="alert">The sheet has no column named {missing.map(c => `“${c}”`).join(', ')}. Pick the new column names below.</p>}

        <h3>Sheet</h3>
        <div className="tf-grid">
          <div className="tf wide sheet-link"><span>Sheet link (saved in .env as ACE_ASSIGN_SHEET_URL)</span>
            <span className="map-inline">
              <input aria-label="Sheet link" value={link ?? source.sheetUrl ?? ''} placeholder="Paste the OneDrive or SharePoint link of the sheet"
                onChange={e => setLink(e.target.value)}/>
              <button className="primary" disabled={!!busy || link === null || !link.trim() || link.trim() === source.sheetUrl} onClick={saveLink}>
                {busy === 'Saving the link…' ? busy : 'Save link'}</button>
              {link !== null && <button className="ghost" disabled={!!busy} onClick={() => setLink(null)}>Cancel</button>}
            </span>
          </div>
          <label className="tf"><span>Read from</span>
            <select value={settings.source} onChange={e => set({source: e.target.value})}>
              <option value="live">Live OneDrive sheet</option>
              <option value="test">Test copy (on this PC)</option>
            </select></label>
          <label className="tf"><span>Sheet tab</span><input value={settings.sheetTab} onChange={e => set({sheetTab: e.target.value})}/></label>
          <label className="tf"><span>Status column</span><ColumnSelect columns={columns} value={settings.statusColumn} onChange={v => set({statusColumn: v})}/></label>
          <label className="tf"><span>Ticket number column (written back)</span><ColumnSelect columns={columns} value={settings.ticketColumn} onChange={v => set({ticketColumn: v})}/></label>
        </div>
        <small>Columns found in the sheet: {columns.join(' · ')}</small>

        <h3>Empty cells: when the sheet leaves one blank</h3>
        <small>A row whose cell is empty for a field set to “No ticket for that row” is never created, by Read sheet,
          Run now or the 30-minute run. It is listed as skipped and gets its ticket once someone fills the cell.</small>
        <div className="map-table">
          <div className="map-head"><span>ACE field</span><span>If the cell is empty</span><span>Rows skipped now</span></div>
          {EMPTY_RULES.map(({field, label, choices}) => <div className="map-row" key={field}>
            <b>{label}<small>{emptyColumn(field)}</small></b>
            <span className="map-inline">
              <select aria-label={`If ${label} is empty`} value={settings.whenEmpty[field]}
                onChange={e => set({whenEmpty: {...settings.whenEmpty, [field]: e.target.value}})}>
                {Object.entries(choices).map(([k, text]) => <option key={k} value={k}>{text}</option>)}
              </select>
              {field === 'assignTo' && settings.whenEmpty.assignTo === 'fallback' &&
                <select aria-label="Fallback assignee" value={settings.fallbackAssignee} onChange={e => set({fallbackAssignee: e.target.value})}>
                  {!employees.includes(settings.fallbackAssignee) && <option>{settings.fallbackAssignee}</option>}
                  {employees.map(e => <option key={e}>{e}</option>)}</select>}
            </span>
            <span className="map-example">{preview.skipped.filter(x => x.reason.includes(label) && x.reason.endsWith('empty')).length}</span>
          </div>)}
        </div>

        <h3>ACE fields</h3>
        <div className="map-table">
          <div className="map-head"><span>ACE field</span><span>Filled from</span><span>Example ({example ? `row ${example._row}` : 'no open row'})</span></div>
          {ACE_FIELDS.map(([field, label]) => <div className="map-row" key={field}>
            <b>{label}{field === 'module' && <small>then Modules below</small>}{field === 'assignTo' && <small>then People below</small>}</b>
            <FieldRule field={field} config={settings.fields[field]} columns={columns} onChange={c => setField(field, c)}/>
            <span className="map-example">{exampleOf(field)}</span>
          </div>)}
        </div>

        <h3>Statuses: sheet → ACE status</h3>
        <small>Which rows get a ticket, and the ACE status it is created with. Every status the sheet uses appears here;
          one set to “No ticket” (or not listed) is left alone. An empty status follows Empty cells above.</small>
        <MappingTable target="ACE status" rows={mappingRows(statusValues(rows, settings), settings.statuses, v => v.toLowerCase())}
          saved={settings.statuses} keyOf={v => v.toLowerCase()} autoOf={() => ''} none="No ticket" countLabel="Rows without a number"
          choices={ace.statuses} onChange={v => set({statuses: v})}/>

        <h3>Modules: sheet → ACE</h3>
        <div className="idea-controls">
          <small>{ace.loadedAt ? `${modules.length} modules from ACE, read ${new Date(ace.loadedAt).toLocaleString('en-IN', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'})}`
            : 'Using a short built-in list until ACE’s modules load.'}</small>
          <button className="ghost small" disabled={!!busy} onClick={refreshAce} title="Opens ACE once to re-read the New Task form lists">
            {busy === 'Reading modules from ACE…' ? busy : 'Refresh from ACE'}</button>
        </div>
        {ace.error && <p className="error" role="alert">{ace.error}</p>}
        <MappingTable target="ACE module" rows={mappingRows(moduleValues, settings.modules)} saved={settings.modules}
          keyOf={v => v} autoOf={v => matchModule(v, modules)} choices={modules} skip onChange={v => set({modules: v})}/>

        <h3>People: sheet → ACE employee</h3>
        <small>{ace.employees === EMPLOYEES ? 'Using the employee list you gave until ACE’s Assign To list loads.' : `${employees.length} employees from ACE’s Assign To list.`}</small>
        <MappingTable target="ACE employee" rows={mappingRows(personValues, settings.people, v => v.toLowerCase())} saved={settings.people}
          keyOf={v => v.toLowerCase()} autoOf={v => matchEmployee(v, employees).name} choices={employees} onChange={v => set({people: v})}/>
        <div className="map-row"><b>(empty)</b><span className="map-example">{settings.whenEmpty.assignTo === 'fallback'
          ? `${settings.fallbackAssignee} (set under Empty cells)` : 'No ticket (set under Empty cells)'}</span><span/></div>
        <small>New modules and names in the sheet appear here on every read, matched automatically when they can be.
          A row whose module or person cannot be matched is never created, even by the 30-minute run, until you set it here.</small>

        <div className="plan-buttons">
          <button className="ghost" disabled={!!busy} onClick={() => setSettings(withDefaults({}))}>Reset to defaults</button>
          <button className="ghost" disabled={!dirty || !!busy} onClick={() => setSettings(saved)}>Undo changes</button>
          <button className="primary" disabled={!dirty || !!busy} onClick={saveSettings}>
            {busy === 'Saving settings…' ? busy : 'Save settings'}</button>
        </div>
      </details>

      {sheet && <section className="panel dash-summary">
        <h2>{drafts.length} {drafts.length === 1 ? 'ticket' : 'tickets'} to create</h2>
        <p>Checked {sheet.total} rows at {sheet.checkedAt} · {sheet.closed} not picked or already have a ticket number · {sheet.skipped.length} skipped (empty cell or module setting)</p>
        <div className="idea-controls">
          <button className="ghost small" onClick={() => setDrafts(ds => ds.map(d => ({...d, pick: !done(d)})))}>Select all</button>
          <button className="ghost small" onClick={() => setDrafts(ds => ds.map(d => ({...d, pick: false})))}>Select none</button>
          <span className="pill">{chosen.length} selected</span>
        </div>
        <div className="plans-scroll-area">
          {drafts.map((d, i) => {
            const off = !!busy || done(d);
            return <article className={'day panel ace-task' + (d.pick ? '' : ' unpicked')} key={d.row}>
              <div className="day-heading">
                <label className="check pick">
                  <input type="checkbox" aria-label={`Create ticket for row ${d.row}`} checked={d.pick} disabled={off}
                    onChange={e => update(i, {pick: e.target.checked})}/>
                  <h3><span className="task-number">Row {d.row}</span> {d.keyword} → {d.assignee || 'who?'}</h3>
                </label>
                {d.outcome && <span className={'result-badge ' + ({saved: 'ok', filled: 'skip'}[d.outcome.status] || 'bad')}>
                  {d.outcome.status === 'saved' ? `Saved${d.outcome.ticket ? ' · ' + d.outcome.ticket : ''}`
                    : d.outcome.status === 'filled' ? 'Filled, not saved' : 'Check ACE'}</span>}
              </div>
              {d.warnings.map((w, k) => <p className="warning" key={k}>{w}</p>)}
              <div className="tf-grid">
                <label className={'tf ' + (!d.assignee ? 'bad' : '')}><span>Assign To<i>*</i></span>
                  <select value={d.assignee} disabled={off} onChange={e => pickPerson(i, e.target.value)}>
                    <option value="">Select…</option>
                    {d.candidates.length > 1 && <optgroup label={`Matches “${d.sheetName}”`}>
                      {d.candidates.map(c => <option key={c} value={c}>{c}</option>)}</optgroup>}
                    <optgroup label="Everyone">{employees.map(e => <option key={e} value={e}>{e}</option>)}</optgroup>
                  </select>
                </label>
                <label className={'tf ' + (!d.module ? 'bad' : '')}><span>Module<i>*</i></span>
                  <select value={d.module} disabled={off} onChange={e => update(i, {module: e.target.value})}>
                    <option value="">Select…</option>
                    {d.module && !modules.includes(d.module) && <option value={d.module}>{d.module} (not in ACE)</option>}
                    {modules.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                </label>
                <label className="tf"><span>Priority<i>*</i></span>
                  <select value={d.priority} disabled={off} onChange={e => update(i, {priority: e.target.value})}>
                    {!['High', 'Medium'].includes(d.priority) && <option>{d.priority}</option>}
                    <option>High</option><option>Medium</option>
                  </select>
                </label>
                <label className="tf"><span>Keyword<i>*</i></span>
                  <input value={d.keyword} maxLength={25} disabled={off} onChange={e => update(i, {keyword: e.target.value})}/>
                </label>
                <label className="tf"><span>Target Date<i>*</i></span>
                  <input type="datetime-local" value={d.targetDate} disabled={off} onChange={e => update(i, {targetDate: e.target.value})}/>
                </label>
                <label className="tf"><span>Effort in Days<i>*</i></span>
                  <input type="number" min="0.5" step="0.5" value={d.effortDays} disabled={off} onChange={e => update(i, {effortDays: e.target.value})}/>
                </label>
              </div>
              <label className="tf wide"><span>Description<i>*</i></span>
                <textarea value={d.description} maxLength={4000} disabled={off} onChange={e => update(i, {description: e.target.value})}/>
              </label>
              <label className="tf wide"><span>Employee Remarks</span>
                <input value={d.employeeRemarks} maxLength={4000} placeholder="." disabled={off} onChange={e => update(i, {employeeRemarks: e.target.value})}/>
              </label>
              <small className="match-reason">
                {d.taskType} · {d.client} · Status {d.status} · {d.assigneeHow === 'default' ? `${HOW.default}, so ${settings.fallbackAssignee}`
                  : d.assigneeHow === 'ask' ? `Sheet says “${d.sheetName}”` : `${HOW[d.assigneeHow]} “${d.sheetName}”`}
              </small>
            </article>;
          })}
        </div>
        {sheet.skipped.length > 0 && <details>
          <summary>{sheet.skipped.length} {sheet.skipped.length === 1 ? 'row' : 'rows'} skipped, no ticket</summary>
          {sheet.skipped.map(s => <p className="dash-muted" key={s.row}>Row {s.row} ({s.reason}): {s.description || '(no description)'}</p>)}
        </details>}
        {issues.length > 0 && <div className="error review-issues" role="alert">{issues.map(x => <p key={x}>{x}</p>)}</div>}
        {chosen.length > 0 && <div className="fill-bar panel">
          <div>
            <label className="check">
              <input type="checkbox" checked={confirmed} disabled={!!busy} onChange={e => setConfirmed(e.target.checked)}/> I reviewed the {chosen.length} selected {chosen.length === 1 ? 'ticket' : 'tickets'}.
            </label>
            <small>Fill only: opens each ticket in its own ACE tab as {source.account || 'the ACE agent'} and checks every field, without saving.
              Create: also clicks Save &amp; Leave Open, finds the new ASPL number and writes it into {settings.ticketColumn} of that row.</small>
          </div>
          <div className="plan-buttons">
            <button className="ghost" disabled={!!busy || issues.length > 0 || !confirmed} onClick={() => send(false)}>Fill only</button>
            <button className="primary" disabled={!!busy || issues.length > 0 || !confirmed} onClick={() => send(true)}>
              {busy === 'Creating tickets in ACE…' ? busy : `Create ${chosen.length} selected in ACE ↗`}
            </button>
          </div>
        </div>}
        {log.length > 0 && <div className="panel dash-summary" aria-live="polite">
          <h3>Result</h3>
          {log.map(l => <p className="dash-muted" key={l}>{l}</p>)}
        </div>}
      </section>}
    </main>
  </div>;
}

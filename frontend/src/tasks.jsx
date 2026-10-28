import React, {useEffect, useState} from 'react';
import {api} from './api';
import {taskIssues, snapOption, TASK_REQUIRED} from './plan';
import {useRecorder} from './recorder';

const DEFAULTS_KEY = 'ace.taskDefaults';
const FIELDS = [['taskType','Task Type'],['priority','Priority'],['frdNature','FRD Nature'],['status','Task Status']];
const TEXTS = [['description','Description'],['clientRemarks','Client Remarks'],['employeeRemarks','Employee Remarks']];
const tidy = s => s.replace(/\s+/g, ' ').trim();

function readDefaults() {
  try {return JSON.parse(localStorage.getItem(DEFAULTS_KEY)) || {};} catch {return {};}
}

function blankTask(defaults) {
  const due = new Date(); due.setDate(due.getDate() + 1); due.setHours(18, 0, 0, 0);
  const pad = n => String(n).padStart(2, '0');
  return {taskType:defaults.taskType||'', priority:defaults.priority||'', client:defaults.client||'', module:defaults.module||'',
    frdNature:'', status:defaults.status||'Open', effortDays:1, keyword:'', description:'', clientRemarks:'', employeeRemarks:'',
    targetDate:`${due.getFullYear()}-${pad(due.getMonth()+1)}-${pad(due.getDate())}T18:00`, warnings:[], source:null};
}

function Choice({label, value, options, disabled, onChange, required, list}) {
  const bad = required && (!value || (options && !options.includes(value)));
  if (list) return <label className={'tf '+(bad?'bad':'')}><span>{label}{required && <i>*</i>}</span>
    <input list={list} value={value} disabled={disabled} placeholder="Type to search…" onChange={e=>onChange(e.target.value)}/>
  </label>;
  return <label className={'tf '+(bad?'bad':'')}><span>{label}{required && <i>*</i>}</span>
    <select value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>
      <option value="">{required ? 'Select…' : '—'}</option>
      {options?.map(o=><option key={o} value={o}>{tidy(o)}</option>)}
    </select>
  </label>;
}

export function TaskApp({modeSwitch, ideaNotes}) {
  const [options, setOptions] = useState(null);
  const [meta, setMeta] = useState({});
  const [notes, setNotes] = useState('');
  const [defaults, setDefaults] = useState(readDefaults);
  const [tasks, setTasks] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [results, setResults] = useState(null);

  async function work(label, fn) {
    setBusy(label); setError('');
    try {await fn();} catch(e) {setError(e.message);} finally {setBusy('');}
  }
  const loadOptions = data => {setOptions(data.options); setMeta({assignee:data.assignee, loadedAt:data.loadedAt});};
  useEffect(() => {api('/task-options').then(loadOptions).catch(e => setError(e.message));}, []);
  useEffect(() => {if (ideaNotes) setNotes(ideaNotes.notes);}, [ideaNotes]);
  useEffect(() => {try {localStorage.setItem(DEFAULTS_KEY, JSON.stringify(defaults));} catch {}}, [defaults]);
  useEffect(() => {setConfirmed(false);}, [tasks]);

  const mic = useRecorder(form => work('Transcribing…', async () => {
    const result = await api('/transcribe', form);
    setNotes(previous => [previous, result.transcript].filter(Boolean).join('\n'));
  }), setError);

  const issues = taskIssues(tasks, options);
  const filled = results?.tasks?.some(t => t.status === 'filled');
  const locked = !!busy || mic.recording;

  const refresh = () => work('Reading options from ACE…', async () => loadOptions(await api('/task-options/refresh', {})));
  const draft = () => work('Drafting tasks…', async () => {
    const res = await api('/tasks/plan', {transcript:notes, defaults});
    setTasks(res.tasks); setResults(null);
  });
  const fill = () => work('Filling ACE tabs…', async () => {
    setResults(await api('/tasks/fill', tasks.map(({warnings, ...t}) => ({...snapAll(t), effortDays:Number(t.effortDays), warnings:[]}))));
    setTimeout(() => document.querySelector('.panel.result')?.scrollIntoView({behavior:'smooth'}), 150);
  });
  const snapAll = t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, options?.[k] ? snapOption(v, options[k]) : v]));
  const update = (i, change) => setTasks(ts => ts.map((t, j) => j === i ? snapAll({...t, ...change}) : t));
  const blankFields = Object.keys(TASK_REQUIRED).filter(f => defaults[f] && tasks.some(t => !t[f]));
  const fillBlanks = () => setTasks(ts => ts.map(t => snapAll({...t,
    ...Object.fromEntries(blankFields.filter(f => !t[f]).map(f => [f, defaults[f]]))})));

  return <div className="app">
    <header>
      <div className="brand-group">
        <span className="brand"><span className="logo">a.</span> ACE <span className="brand-sub">/ task creator</span></span>
        {modeSwitch}
      </div>
      <div className="rhythm-badge">
        <span className="sun">👤</span> <span>Assign to</span> <strong>{meta.assignee || '…'}</strong>
      </div>
      <div className="steps-compact">
        <span className="active">01 <b>Describe</b></span>
        <span className={tasks.length?'active':''}>02 <b>Review</b></span>
        <span className={results?'active':''}>03 <b>Fill in ACE</b></span>
      </div>
    </header>

    <main className="workspace-main">
      <div className="col-compose">
        <section className="compose panel">
          <div className="section-heading"><h2>Which tasks should be created?</h2></div>
          <textarea className="notes" aria-label="Task notes" maxLength={20000} disabled={locked} value={notes}
            onChange={e=>setNotes(e.target.value)}
            placeholder={'Say or type the tickets, e.g.\n“Aster RV, EMR module: vitals not saving on nurse workbench, high priority, 2 days, by Friday.\nSecond one – Akhil Cloud billing, discount rounding wrong on final bill, medium.”'}/>
          <div className="compose-footer">
            <button className={'mic '+(mic.recording?'recording':'')} disabled={!!busy || !options} onClick={mic.toggle}>
              <span>{mic.recording?'■':'◉'}</span> {mic.recording?`Stop · ${mic.seconds}s`:'Speak the tasks'}
            </button>
            <span>Text and voice only · no git or file scan</span>
          </div>

          <div className="defaults">
            <span className="eyebrow">DEFAULTS WHEN NOT SAID</span>
            <div className="tf-grid">
              <Choice label="Client" list="ace-clients" value={defaults.client||''} options={options?.client} disabled={locked} onChange={v=>setDefaults({...defaults, client:v})}/>
              <Choice label="Module" list="ace-modules" value={defaults.module||''} options={options?.module} disabled={locked} onChange={v=>setDefaults({...defaults, module:v})}/>
              <Choice label="Task Type" value={defaults.taskType||''} options={options?.taskType} disabled={locked} onChange={v=>setDefaults({...defaults, taskType:v})}/>
              <Choice label="Priority" value={defaults.priority||''} options={options?.priority} disabled={locked} onChange={v=>setDefaults({...defaults, priority:v})}/>
            </div>
          </div>

          <div className="plan-action">
            <span>{meta.loadedAt ? `Options read from ACE ${new Date(meta.loadedAt).toLocaleDateString('en-IN')}` : 'Options from saved ACE form'}</span>
            <div className="plan-buttons">
              <button className="ghost" disabled={locked} onClick={refresh} title="Opens ACE once to re-read clients, modules and statuses">
                {busy.startsWith('Reading')?busy:'Refresh from ACE'}
              </button>
              <button className="ghost" disabled={locked || !options || filled} onClick={()=>setTasks(ts=>[...ts, blankTask(defaults)])}>+ Blank task</button>
              <button className="primary" disabled={locked || !notes.trim() || !options || filled} onClick={draft}>
                {busy.startsWith('Drafting')?busy:'Draft tasks'} <span>↗</span>
              </button>
            </div>
          </div>
        </section>
        {error && <div role="alert" className="error">{error}</div>}
      </div>

      <div className="col-review">
        {!tasks.length && !results && (
          <div className="standby panel">
            <div className="standby-icon">🎫</div>
            <h3>Ready to draft ACE tasks</h3>
            <p>Describe one or more tickets on the left and click <b>Draft tasks</b>. Each draft is matched to the exact ACE client, module and status names. You can edit everything before filling.</p>
            <div className="standby-tips">
              <span className="tip-badge">Safe</span>
              <small>Each task opens in its own ACE tab with <b>{meta.assignee || 'you'}</b> ticked in Assign To. Nothing is saved; you click <b>Save &amp; Leave Open</b> after review.</small>
            </div>
          </div>
        )}

        {!!tasks.length && (
          <section className="preview">
            <div className="preview-top-bar">
              <div><span className="eyebrow">MAKE IT YOURS</span><h2>Review your tasks</h2></div>
              {blankFields.length>0 && !filled && <button className="ghost small" disabled={locked} onClick={fillBlanks}
                title="Uses the defaults on the left for every task where that field is empty">
                Fill empty {blankFields.map(f=>TASK_REQUIRED[f]).join(', ')} from defaults</button>}
              <span className="pill">{tasks.length} {tasks.length===1?'task':'tasks'} · assigned to {meta.assignee}</span>
            </div>
            <div className="plans-scroll-area">
              {tasks.map((t, i) => {
                const off = locked || filled;
                return <article className="day panel ace-task" key={i}>
                  <div className="day-heading">
                    <h3><span className="task-number">{String(i+1).padStart(2,'0')}</span> {t.keyword || 'New task'}</h3>
                    <button className="ghost small" disabled={off} onClick={()=>setTasks(ts=>ts.filter((_, j)=>j!==i))}>Remove</button>
                  </div>
                  {t.warnings?.map((w, k) => <p className="warning" key={k}>{w}</p>)}
                  <div className="tf-grid">
                    <Choice label="Client Name" required list="ace-clients" value={t.client} options={options?.client} disabled={off} onChange={v=>update(i,{client:v})}/>
                    <Choice label="Module" required list="ace-modules" value={t.module} options={options?.module} disabled={off} onChange={v=>update(i,{module:v})}/>
                    {FIELDS.map(([f, label]) => <Choice key={f} label={label} required={f!=='frdNature'} value={t[f]} options={options?.[f]} disabled={off} onChange={v=>update(i,{[f]:v})}/>)}
                    <label className={'tf '+(!t.targetDate?'bad':'')}><span>Target Date<i>*</i></span>
                      <input type="datetime-local" value={t.targetDate} disabled={off} onChange={e=>update(i,{targetDate:e.target.value})}/>
                    </label>
                    <label className={'tf '+(!(Number(t.effortDays)>0)?'bad':'')}><span>Effort in Days<i>*</i></span>
                      <input type="number" min="0.1" step="0.5" value={t.effortDays} disabled={off} onChange={e=>update(i,{effortDays:e.target.value})}/>
                    </label>
                    <label className={'tf '+(!t.keyword?.trim()?'bad':'')}><span>Keyword<i>*</i></span>
                      <input value={t.keyword} maxLength={100} disabled={off} onChange={e=>update(i,{keyword:e.target.value})}/>
                    </label>
                  </div>
                  {TEXTS.map(([f, label]) => <label className={'tf wide '+(!t[f]?.trim()?'bad':'')} key={f}>
<span>{label}<i>*</i></span>
                    <textarea value={t[f]} maxLength={4000} disabled={off} onChange={e=>update(i,{[f]:e.target.value})}/>
                  </label>)}
                  {t.source && <small className="match-reason">From your notes: “{t.source}”</small>}
                </article>;
              })}
            </div>

            {issues.length > 0 && <div className="error" role="alert">{issues.map(x=><p key={x}>{x}</p>)}</div>}

            <div className="fill-bar panel">
              <div>
                <label className="check">
                  <input type="checkbox" checked={confirmed} disabled={!!busy} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed every task, client, module and date.
                </label>
                <small>Opens one ACE tab per task, fills it and ticks {meta.assignee}. It never clicks Save.</small>
              </div>
              <button className="primary" disabled={!!busy || issues.length>0 || !confirmed} onClick={fill}>
                {busy.startsWith('Filling')?busy:filled?'Re-verify ACE tabs ↗':'Fill in ACE ↗'}
              </button>
            </div>
          </section>
        )}

        {results && (
          <section className="panel result" aria-live="polite">
            <h2>Portal handoff</h2>
            {results.tasks.map(r => {
              const ok = r.status === 'filled';
              return <article className={'result-day '+(ok?'ok':'bad')} key={r.index}>
                <div className="result-head">
                  <strong>Task {r.index} · {r.keyword}</strong>
                  <span className={'result-badge '+(ok?'ok':'bad')}>{ok?'Filled — review & Save in ACE':'Interrupted'}</span>
                </div>
                <p>{r.message}</p>
                {r.screenshotUrl && <a className="screenshot-link" href={r.screenshotUrl} target="_blank" rel="noreferrer">📸 View filled form ↗</a>}
              </article>;
            })}
            {results.notStarted.length > 0 && <p className="warning">Not started: task {results.notStarted.join(', ')}</p>}
            <p className="warning">Keep this app and the ACE tabs open until you have clicked Save & Leave Open on each. Nothing has been saved by this app.</p>
            <button className="ghost" disabled={!!busy} onClick={()=>{setTasks([]); setResults(null); setNotes('');}}>Start new batch</button>
          </section>
        )}
      </div>
    </main>

    <datalist id="ace-clients">{options?.client.map(o=><option key={o} value={o}/>)}</datalist>
    <datalist id="ace-modules">{options?.module.map(o=><option key={o} value={o}/>)}</datalist>
    {busy && <div role="status" className="status"><span className="spinner"/>{busy}</div>}
    <footer>
      <span>ACE TASK CREATOR</span>
      <span>Drafts only · Save stays with you</span>
      <span>Your review. Your final say.</span>
    </footer>
  </div>;
}

import React, {useEffect, useState} from 'react';
import {api} from './api';
import {taskIssues, snapOption, markDone, completionIssues, aceTask, groupIssues, TASK_REQUIRED} from './plan';
import {useRecorder} from './recorder';
import {readStored, writeStored} from './agent';

const DEFAULTS_KEY = 'ace.taskDefaults';
const FIELDS = [['taskType','Task Type'],['priority','Priority'],['frdNature','FRD Nature'],['status','Task Status']];
const TEXTS = [['description','Description'],['clientRemarks','Client Remarks'],['employeeRemarks','Employee Remarks']];
const tidy = s => s.replace(/\s+/g, ' ').trim();
// Defaults for tickets that back your own work (Ticket ideas, timesheet rows).
const OWN_WORK = {taskType:'New Requirement', priority:'Medium', client:'Augastam (New Product)', module:'Augastam ai', status:'Open'};

function readDefaults() {
  try {return JSON.parse(localStorage.getItem(DEFAULTS_KEY)) || {};} catch {return {};}
}

function blankTask(defaults) {
  const due = new Date(); due.setDate(due.getDate() + 1); due.setHours(18, 0, 0, 0);
  const pad = n => String(n).padStart(2, '0');
  return {taskType:defaults.taskType||'', priority:defaults.priority||'', client:defaults.client||'', module:defaults.module||'',
    frdNature:'', status:defaults.status||'Open', effortDays:1, keyword:'', description:'', clientRemarks:'.', employeeRemarks:'.',
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

export function TaskApp({modeSwitch, ideaNotes, ticketJob, onLinked}) {
  const [options, setOptions] = useState(null);
  const [meta, setMeta] = useState({});
  const [notes, setNotes] = useState('');
  const [defaults, setDefaults] = useState(readDefaults);
  const [tasks, setTasks] = useState([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [agents, setAgents] = useState([]);
  const [agent, setAgent] = useState(() => readStored('ace.agent', ''));
  const [known, setKnown] = useState([]);

  async function work(label, fn) {
    setBusy(label); setError('');
    try {await fn();} catch(e) {setError(e.message);} finally {setBusy('');}
  }
  const loadOptions = data => {setOptions(data.options); setMeta({assignee:data.assignee, loadedAt:data.loadedAt});};
  useEffect(() => {
    api('/task-options').then(loadOptions).catch(e => setError(e.message));
    api('/agent/agents').then(list => {
      const usable = list.filter(a => a.installed && a.verified);
      setAgents(usable);
      setAgent(current => usable.some(a => a.id === current) ? current : usable[0]?.id || '');
    }).catch(() => setAgents([]));
  }, []);
  useEffect(() => {if (agent) writeStored('ace.agent', agent);}, [agent]);
  // Unsaved ACE tabs are still waiting for you; a new batch would lose track of them.
  const batchOpen = () => {
    if (!tasks.some(t => t.outcome?.status === 'filled')) return false;
    setError('Some tickets are still waiting in ACE tabs. Save them and choose Start new batch, then create tickets again.');
    return true;
  };
  // Tickets an assigned ticket already covers start unticked.
  const load = list => {setTasks(list.map(t => ({...t, pick:!t.existingTicket}))); setKnown([]);};
  // Your own past work: ask whether each ticket is already completed before it goes into ACE.
  const asked = list => list.map(t => ({...t, askDone:true, done:null}));
  // "Create tickets" on Ticket ideas: draft straight away from the selected activity.
  useEffect(() => {
    if (!ideaNotes) return;
    setNotes(ideaNotes.notes);
    if (!batchOpen()) draft(ideaNotes.notes, true);
  }, [ideaNotes]);
  // "Create tickets" on the Timesheet tab: one draft per untagged row, linked back to that row.
  useEffect(() => {
    if (!ticketJob || batchOpen()) return;
    work('Drafting tickets for your timesheet…', async () => {
      const res = await api('/tasks/from-timesheet', {days:ticketJob.rows});
      load(asked(res.tasks)); setKnown(res.known);
    });
  }, [ticketJob]);
  useEffect(() => {try {localStorage.setItem(DEFAULTS_KEY, JSON.stringify(defaults));} catch {}}, [defaults]);
  useEffect(() => {setConfirmed(false);}, [tasks]);

  const mic = useRecorder(form => work('Transcribing…', async () => {
    const result = await api('/transcribe', form);
    setNotes(previous => [previous, result.transcript].filter(Boolean).join('\n'));
  }), setError);

  const finished = t => ['filled', 'saved', 'unconfirmed'].includes(t.outcome?.status);
  const chosen = tasks.map((_, i) => i).filter(i => tasks[i].pick && !finished(tasks[i]));
  const picked = chosen.map(i => tasks[i]), numbers = chosen.map(i => i + 1);
  const issues = !chosen.length ? (tasks.some(t => !finished(t)) ? ['Tick at least one ticket to create.'] : [])
    : [...taskIssues(picked, options, numbers), ...completionIssues(picked, numbers)];
  const unanswered = picked.filter(t => t.askDone && t.done == null).length;
  const handled = tasks.filter(t => t.outcome);
  const filled = handled.length > 0;
  const covered = tasks.filter(t => t.existingTicket).length;
  const locked = !!busy || mic.recording;

  const refresh = () => work('Reading options from ACE…', async () => loadOptions(await api('/task-options/refresh', {})));
  const draft = (text = notes, ask = false) => work(`Drafting tasks with ${agents.find(a => a.id === agent)?.label || 'your agent'}…`, async () => {
    if (!agent) throw new Error('No coding agent is set up. Run setup_agents.ps1, then reload.');
    // Empty defaults fall back to the user's standard ticket values; anything set on the left wins.
    const res = await api('/tasks/plan', {transcript:text, defaults:ask ? OWN_WORK : effective, agent, checkExisting:ask});
    load(ask ? asked(res.tasks) : res.tasks);
  });
  // save: fill, check and Save & Leave Open each ticket; otherwise fill only and you save in ACE.
  const send = save => work(save ? 'Creating tickets in ACE…' : 'Filling ACE tabs…', async () => {
    const sent = chosen;
    const res = await api(save ? '/tasks/create' : '/tasks/fill', sent.map(i => aceTask(snapAll(tasks[i]))));
    const outcomes = Object.fromEntries(res.tasks.map(r => [sent[r.index - 1], r]));
    setTasks(ts => ts.map((t, i) => outcomes[i] ? {...t, outcome:outcomes[i],
      linkedTicket:t.link && outcomes[i].ticket ? outcomes[i].ticket : t.linkedTicket} : t));
    const links = res.tasks.filter(r => r.ticket && tasks[sent[r.index - 1]].link)
      .map(r => ({...tasks[sent[r.index - 1]].link, ticket:r.ticket}));
    if (links.length) onLinked({links, tickets:res.tickets || []}, false);
    if (res.notStarted?.length) setError(`Stopped after a problem; ticket ${res.notStarted.map(n => sent[n - 1] + 1).join(', ')} not started.`);
    setTimeout(() => document.querySelector('.panel.result')?.scrollIntoView({behavior:'smooth'}), 150);
  });
  const snapAll = t => Object.fromEntries(Object.entries(t).map(([k, v]) => [k, options?.[k] ? snapOption(v, options[k]) : v]));
  const linkable = tasks.map((_, i) => i).filter(i => tasks[i].outcome?.status === 'filled' && tasks[i].link && !tasks[i].linkedTicket);
  const link = () => work('Reading your new tickets from ACE…', async () => {
    const res = await api('/tasks/link-tickets', {descriptions:linkable.map(i => tasks[i].description), known});
    const links = linkable.map((i, k) => ({...tasks[i].link, ticket:res.links[k]}));
    setTasks(ts => ts.map((t, i) => {const k = linkable.indexOf(i); return k >= 0 && res.links[k] ? {...t, linkedTicket:res.links[k]} : t;}));
    const missing = linkable.filter((i, k) => !res.links[k]).map(i => i + 1);
    onLinked({links, tickets:res.tickets}, !missing.length);
    if (missing.length) setError(`No saved ticket found yet for task ${missing.join(', ')}. Click Save & Leave Open in its ACE tab, then link again.`);
  });
  const setPick = value => setTasks(ts => ts.map(t => finished(t) ? t : {...t, pick:value}));
  const update = (i, change) => setTasks(ts => ts.map((t, j) => j === i ? snapAll({...t, ...change}) : t));
  const effective = {...OWN_WORK, ...Object.fromEntries(Object.entries(defaults).filter(([, v]) => v))};
  const blankFields = Object.keys(TASK_REQUIRED).filter(f => effective[f] && tasks.some(t => !finished(t) && !t[f]));
  const fillBlanks = () => setTasks(ts => ts.map(t => finished(t) ? t : snapAll({...t,
    ...Object.fromEntries(blankFields.filter(f => !t[f]).map(f => [f, effective[f]]))})));

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
        <span className={filled?'active':''}>03 <b>Create in ACE</b></span>
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
              <select aria-label="Agent" value={agent} disabled={locked || !agents.length} onChange={e=>setAgent(e.target.value)}>
                {!agents.length && <option value="">No agent set up</option>}
                {agents.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
              <button className="primary" disabled={locked || !notes.trim() || !options || filled || !agent} onClick={() => draft()}>
                {busy.startsWith('Drafting')?busy:'Draft tasks'} <span>↗</span>
              </button>
            </div>
          </div>
        </section>
        {error && <div role="alert" className="error">{error}</div>}
      </div>

      <div className="col-review">
        {!tasks.length && (
          <div className="standby panel">
            <div className="standby-icon">🎫</div>
            <h3>Ready to draft ACE tasks</h3>
            <p>Describe one or more tickets on the left and click <b>Draft tasks</b>. Each draft is matched to the exact ACE client, module and status names. You can edit everything before filling.</p>
            <div className="standby-tips">
              <span className="tip-badge">Safe</span>
              <small>You review every field and tick the tickets you want. Only then does <b>Create selected in ACE</b> fill, check and save each one with <b>{meta.assignee || 'you'}</b> ticked in Assign To.</small>
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
              {unanswered>0 && <button className="ghost small" disabled={locked}
                onClick={()=>setTasks(ts=>ts.map(t => t.pick && !finished(t) && t.askDone && t.done == null ? markDone(t, true, options?.status) : t))}>
                Mark {unanswered} selected completed</button>}
              <div className="pick-tools">
                <button className="ghost small" disabled={locked} onClick={()=>setPick(true)}>Select all</button>
                <button className="ghost small" disabled={locked || !chosen.length} onClick={()=>setPick(false)}>Select none</button>
                <span className="pill">{chosen.length} of {tasks.length} selected · assigned to {meta.assignee}</span>
              </div>
            </div>
            {covered > 0 && <p className="hint">{covered} {covered===1?'piece of work is':'pieces of work are'} already covered by a ticket assigned to you, so {covered===1?'it starts':'they start'} unticked. Tick one only if it really needs a new ticket.</p>}
            <div className="plans-scroll-area">
              {tasks.map((t, i) => {
                const off = locked || finished(t);
                return <article className={'day panel ace-task'+(t.pick?'':' unpicked')} key={i}>
                  <div className="day-heading">
                    <label className="check pick">
                      <input type="checkbox" aria-label={`Create ticket ${i+1}`} checked={!!t.pick} disabled={off}
                        onChange={e=>setTasks(ts=>ts.map((x, j)=>j===i?{...x, pick:e.target.checked}:x))}/>
                      <h3><span className="task-number">{String(i+1).padStart(2,'0')}</span> {t.keyword || 'New task'}</h3>
                    </label>
                    {t.outcome ? <span className={'result-badge '+(t.outcome.status==='saved'?'ok':t.outcome.status==='filled'?'skip':'bad')}>
                      {t.outcome.status==='saved' ? `Saved${t.outcome.ticket ? ' · '+t.outcome.ticket : ''}` : t.outcome.status==='filled' ? 'Filled, not saved' : 'Check ACE'}</span>
                      : <button className="ghost small" disabled={off} onClick={()=>setTasks(ts=>ts.filter((_, j)=>j!==i))}>Remove</button>}
                  </div>
                  {t.existingTicket && <p className="covered">Already covered by <b>{t.existingTicket}</b>, assigned to you. No new ticket needed unless you tick it.</p>}
                  {t.warnings?.map((w, k) => <p className="warning" key={k}>{w}</p>)}
                  {t.askDone && <div className={'done-question '+(t.done == null ? 'bad' : '')}>
                    <span>Have you completed this?{t.workDate && <small> Work done on {new Date(t.workDate+'T12:00:00').toLocaleDateString('en-IN',{weekday:'short', day:'numeric', month:'short'})}.</small>}</span>
                    <div className="switch">
                      <button disabled={off} className={t.done===true?'selected':''} onClick={()=>setTasks(ts=>ts.map((x, j)=>j===i?markDone(x, true, options?.status):x))}>Yes, completed</button>
                      <button disabled={off} className={t.done===false?'selected':''} onClick={()=>setTasks(ts=>ts.map((x, j)=>j===i?markDone(x, false, options?.status):x))}>Not yet</button>
                    </div>
                  </div>}
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
                      <input value={t.keyword} maxLength={25} disabled={off} onChange={e=>update(i,{keyword:e.target.value})}/>
                    </label>
                  </div>
                  {TEXTS.map(([f, label]) => <label className={'tf wide '+(!t[f]?.trim()?'bad':'')} key={f}>
<span>{label}<i>*</i></span>
                    <textarea value={t[f]} maxLength={4000} disabled={off} onChange={e=>update(i,{[f]:e.target.value})}/>
                  </label>)}
                  {t.source && <small className="match-reason">From your notes: “{t.source}”</small>}
                  {t.link && <small className="match-reason">For your timesheet on {t.link.date} · task {t.link.index + 1}{t.linkedTicket ? ` · linked to ${t.linkedTicket}` : ''}</small>}
                </article>;
              })}
            </div>

            {issues.length > 0 && <div className="error review-issues" role="alert">{groupIssues(issues).map(x=><p key={x}>{x}</p>)}</div>}

            {chosen.length > 0 && <div className="fill-bar panel">
              <div>
                <label className="check">
                  <input type="checkbox" checked={confirmed} disabled={!!busy} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed every field of the {chosen.length} selected {chosen.length===1?'ticket':'tickets'}.
                </label>
                <small>Fills each one in ACE, checks every field and {meta.assignee} in Assign To, then clicks Save &amp; Leave Open.</small>
              </div>
              <div className="plan-buttons">
                <button className="ghost" disabled={!!busy || issues.length>0 || !confirmed} onClick={()=>send(false)}
                  title="Fill and check in ACE tabs; you click Save & Leave Open yourself">Fill only</button>
                <button className="primary" disabled={!!busy || issues.length>0 || !confirmed} onClick={()=>send(true)}>
                  {busy.startsWith('Creating')?busy:`Create ${chosen.length} selected in ACE ↗`}
                </button>
              </div>
            </div>}
          </section>
        )}

        {filled && (
          <section className="panel result" aria-live="polite">
            <h2>In ACE</h2>
            {tasks.map((t, i) => t.outcome && [t, i]).filter(Boolean).map(([t, i]) => {
              const r = t.outcome;
              const meta = {saved:{cls:'ok', label:r.ticket ? `Saved · ${r.ticket}` : 'Saved'},
                filled:{cls:'skip', label:'Filled — Save it in ACE'}, unconfirmed:{cls:'bad', label:'Check this ACE tab'},
                interrupted:{cls:'bad', label:'Interrupted'}}[r.status] || {cls:'bad', label:r.status};
              return <article className={'result-day '+meta.cls} key={i}>
                <div className="result-head">
                  <strong>Ticket {i+1} · {t.keyword}</strong>
                  <span className={'result-badge '+meta.cls}>{meta.label}</span>
                </div>
                <p>{r.message}</p>
                {r.screenshotUrl && <a className="screenshot-link" href={r.screenshotUrl} target="_blank" rel="noreferrer">📸 View the form in ACE ↗</a>}
              </article>;
            })}
            {tasks.some(t => t.outcome?.status === 'filled') && <p className="warning">Keep this app and the ACE tabs open until you have clicked Save & Leave Open on each filled ticket.</p>}
            {linkable.length > 0 && <div className="draft-notice panel">
              <span>After you click <b>Save &amp; Leave Open</b> in each ACE tab, bring the new ticket numbers into your timesheet.</span>
              <button className="primary" disabled={!!busy} onClick={link}>{busy.startsWith('Reading your')?busy:'Link saved tickets ↗'}</button>
            </div>}
            <button className="ghost" disabled={!!busy} onClick={()=>{setTasks([]); setNotes(''); setKnown([]);}}>Start new batch</button>
          </section>
        )}
      </div>
    </main>

    <datalist id="ace-clients">{options?.client.map(o=><option key={o} value={o}/>)}</datalist>
    <datalist id="ace-modules">{options?.module.map(o=><option key={o} value={o}/>)}</datalist>
    {busy && <div role="status" className="status"><span className="spinner"/>{busy}</div>}
    <footer>
      <span>ACE TASK CREATOR</span>
      <span>Saves only the tickets you tick</span>
      <span>Your review. Your final say.</span>
    </footer>
  </div>;
}

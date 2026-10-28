import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {total, validation, tagTask, adjustLongDay} from './plan';
import {api, streamEvents} from './api';
import {agentPayload, mergeIncomingDraft, newDrafts, readStored, writeStored} from './agent';
import {TaskApp} from './tasks';
import {Dashboard} from './dashboard';
import {TicketIdeas} from './ticket-ideas';
import './style.css';

async function streamPlan(path, payload, onStep) {
  const result = await streamEvents(path, payload, onStep, 'Failed to start planning stream.');
  const plan = result?.plan || result?.plans;
  if (!plan) throw new Error('Planning ended without generating tasks. Please try again.');
  return plan;
}

function App({modeSwitch, jump}) {
  const [date, setDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [range, setRange] = useState(false);
  const [notes, setNotes] = useState('');
  const [perDayMode, setPerDayMode] = useState(false);
  const [perDay, setPerDay] = useState({});
  const [plans, setPlans] = useState([]);
  const [tickets, setTickets] = useState([]);
  const [ticketLoading, setTicketLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [results, setResults] = useState(null);
  const [savedDays, setSavedDays] = useState({});
  const [confirmed, setConfirmed] = useState(false);
  const [health, setHealth] = useState(null);
  const [fillAttempted, setFillAttempted] = useState(false);
  const [streamSteps, setStreamSteps] = useState([]);
  const [isStreamingPlan, setIsStreamingPlan] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [agents, setAgents] = useState([]);
  const [agent, setAgent] = useState(() => readStored('ace.agent', ''));
  const [edited, setEdited] = useState({});
  const [noWork, setNoWork] = useState([]);
  const [skipped, setSkipped] = useState([]);
  const [agentRunning, setAgentRunning] = useState(false);
  const [draftNotice, setDraftNotice] = useState(null);
  const recorder = useRef(null), recordingTimer = useRef(null), streams = useRef(null), streamFeedRef = useRef(null);
  const pendingDraft = useRef(null);
  useEffect(() => {
    api('/health').then(h => {setHealth(h); setDate(h.today); setToDate(h.today);}).catch(e => setError(e.message));
    api('/agent/agents').then(list => {
      const usable = list.filter(a => a.installed && a.verified);
      setAgents(usable);
      setAgent(current => usable.some(a => a.id === current) ? current : usable[0]?.id || '');
    }).catch(() => setAgents([]));
    loadTickets();
    return () => {clearInterval(recordingTimer.current); streams.current?.getTracks().forEach(t=>t.stop());};
  }, []);
  // "Fill this day" on the dashboard: open that date in single-day mode, unless a fill is already under way.
  useEffect(() => {
    if (!jump) return;
    if (fillAttempted || busy || recording) {
      setError(`Finish or reload the current fill before switching to ${jump.date}.`);
      return;
    }
    setRange(false); setDate(jump.date); setError('');
  }, [jump]);
  useEffect(() => {setConfirmed(false);}, [plans]);
  // A plan belongs to the date/range it was built for. If the date changes,
  // drop the stale plan so the preview can never show a different date's tasks.
  useEffect(() => {
    const waiting = pendingDraft.current;
    pendingDraft.current = null;
    setPlans(waiting && !range && waiting.date === date ? [waiting] : []);
    setResults(null); setFillAttempted(false); setStreamSteps([]); setEdited({}); setNoWork([]);
  }, [date, toDate, range]);
  useEffect(() => {writeStored('ace.agent', agent);}, [agent]);
  // Drafts can also arrive from chat ("fill my ACE for …"); pick them up without overwriting edits.
  useEffect(() => {
    if (busy || isStreamingPlan || fillAttempted || recording) return;
    let active = true;
    const check = async () => {
      if (document.hidden || draftNotice) return;
      try {
        const fresh = newDrafts(await api('/agent/drafts'), readStored('ace.agentDraftsSeen', {}));
        if (!active || !fresh.length) return;
        const draft = await api(`/agent/drafts/${fresh[0].date}`);
        if (!active) return;
        const createdAt = fresh[0].createdAt;
        if (inView(draft.date) && !edited[draft.date]) {
          setPlans(current => mergeIncomingDraft(current, draft, false).plans);
          markSeen(draft.date, createdAt);
        } else {
          setDraftNotice({draft, createdAt, text:`A new draft from your agent for ${draft.date} is ready. Load it?`});
        }
      } catch (_) { /* Older servers have no agent routes; try again later. */ }
    };
    check();
    const timer = setInterval(check, 15000);
    return () => {active = false; clearInterval(timer);};
  }, [busy, isStreamingPlan, fillAttempted, recording, draftNotice, edited, date, toDate, range]);
  useEffect(() => {
    if (streamFeedRef.current) {
      streamFeedRef.current.scrollTop = streamFeedRef.current.scrollHeight;
    }
  }, [streamSteps]);
  useEffect(() => {
    if (!fillAttempted) return;
    const prevent = e => {e.preventDefault(); e.returnValue = '';};
    window.addEventListener('beforeunload', prevent);
    return () => window.removeEventListener('beforeunload', prevent);
  }, [fillAttempted]);
  useEffect(() => {
    const pending = results?.days?.filter(d => d.status === 'filled' && savedDays[d.date]?.status !== 'filled') || [];
    if (!pending.length) return;
    let active = true;
    let cursor = 0;
    const check = async () => {
      if (document.hidden || busy) return;
      const day = pending[cursor++ % pending.length];
      try {
        const status = await api('/status/check-day', {day:day.date});
        if (active) setSavedDays(prev => ({...prev, [day.date]:status}));
      } catch (_) { /* Keep the draft state until ACE can be checked again. */ }
    };
    check();
    const timer = setInterval(check, 15000);
    return () => {active = false; clearInterval(timer);};
  }, [results, savedDays, busy]);
  const issues = validation(plans);
  const adjustableDays = plans.filter(p => adjustLongDay(p) !== p);
  const days = [];
  if (range && date && toDate) {
    const last = new Date(toDate + 'T12:00:00Z');
    for (let d = new Date(date + 'T12:00:00Z'), i=0; d <= last && i<63; d.setUTCDate(d.getUTCDate()+1),i++) {
      if (d.getUTCDay() !== 0) days.push(d.toISOString().slice(0,10));
    }
  }
  const invalidRange = range && (!days.length || (new Date(toDate)-new Date(date))/86400000 > 62 || toDate < date);
  async function work(label, fn) {
    setBusy(label); setError('');
    try {await fn();} catch(e) {setError(e.message);} finally {setBusy('');}
  }
  async function buildPlan() {
    setStreamSteps([]);
    setIsStreamingPlan(true);
    setBusy('Analyzing system activity…');
    setError('');
    const streamPath = range ? '/plan-range-stream' : '/plan-stream';
    const payload = range
      ? {fromDate:date, toDate, notes:perDayMode ? '' : notes, perDay:perDayMode ? perDay : {}}
      : {date, transcript:notes};

    try {
      const result = await streamPlan(streamPath, payload, step => {
        setStreamSteps(prev => [...prev, step]);
        setBusy(step.step);
      });
      setPlans(Array.isArray(result) ? result : [result]);
      setEdited({});
      setResults(null);
    } catch(e) {
      setError(e.message);
    } finally {
      setIsStreamingPlan(false);
      setBusy('');
    }
  }
  function inView(day) {
    return range ? day >= date && day <= toDate : day === date;
  }
  function markSeen(day, createdAt) {
    writeStored('ace.agentDraftsSeen', {...readStored('ace.agentDraftsSeen', {}), [day]:createdAt});
  }
  async function buildWithAgent() {
    setStreamSteps([]); setIsStreamingPlan(true); setAgentRunning(true); setNoWork([]); setSkipped([]); setDraftNotice(null);
    setBusy('Your agent is reading your work…'); setError('');
    try {
      const result = await streamEvents('/agent/draft-stream',
        agentPayload({date, toDate, range, notes, perDayMode, perDay, agent}),
        step => {setStreamSteps(prev => [...prev, step]); setBusy(step.step);}, 'Failed to start your agent.');
      if (!result) throw new Error('Your agent stopped without a result. Please try again.');
      setPlans(result.plans); setEdited({}); setNoWork(result.noWork || []); setSkipped(result.skipped || []); setResults(null);
      const listed = await api('/agent/drafts').catch(() => []);
      listed.filter(d => result.plans.some(p => p.date === d.date)).forEach(d => markSeen(d.date, d.createdAt));
    } catch(e) {
      setError(e.message);
    } finally {
      setIsStreamingPlan(false); setAgentRunning(false); setBusy('');
    }
  }
  function loadDraft({draft, createdAt}) {
    setDraftNotice(null); markSeen(draft.date, createdAt); setEdited(e => ({...e, [draft.date]:false}));
    if (inView(draft.date)) {
      setPlans(current => mergeIncomingDraft(current, draft, false).plans);
    } else {
      pendingDraft.current = draft; setRange(false); setDate(draft.date);
    }
  }
  async function loadTickets() {
    setTicketLoading(true);
    try {
      setTickets(await api('/tickets'));
    } catch (e) {
      setError(`Could not load tickets from ACE: ${e.message}`);
    } finally {
      setTicketLoading(false);
    }
  }
  async function fillPlans() {
    await work('Filling ACE…', async () => {
      setResults(null);
      await api('/validate', plans);
      const res = await api('/fill', plans);
      setSavedDays({});
      setResults(res);
      if (res.days?.some(d => d.status === 'filled')) {
        setFillAttempted(true);
      }
      setTimeout(() => document.querySelector('.panel.result')?.scrollIntoView({behavior:'smooth'}), 150);
    });
  }
  async function startRecording() {
    if (recording) {recorder.current?.stop(); return;}
    setError('');
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('Microphone recording is unavailable. Use Chrome on localhost or type your notes.');
      const stream = await navigator.mediaDevices.getUserMedia({audio:true}); streams.current = stream;
      const mime = ['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
      if (!mime) {stream.getTracks().forEach(t=>t.stop()); throw new Error('No supported recording format. Please type your notes.');}
      const capture = new MediaRecorder(stream, {mimeType:mime}); recorder.current = capture;
      const chunks = []; capture.ondataavailable = e => {if(e.data.size) chunks.push(e.data);};
      capture.onstop = async () => {
        clearInterval(recordingTimer.current); stream.getTracks().forEach(t=>t.stop()); setRecording(false);
        await work('Transcribing…', async () => {
          const form = new FormData(); const base = mime.split(';')[0];
          form.append('audio', new Blob(chunks, {type:base}), 'recording');
          const result = await api('/transcribe', form);
          setNotes(previous => [previous, result.transcript].filter(Boolean).join('\n'));
        });
      };
      capture.start(); setRecording(true); setSeconds(0);
      let elapsed = 0;
      recordingTimer.current = setInterval(()=> {setSeconds(++elapsed); if(elapsed>=28 && capture.state==='recording') capture.stop();},1000);
    } catch(e) {setError(e.message); streams.current?.getTracks().forEach(t=>t.stop());}
  }
  function updateTask(dayIndex, taskIndex, change) {
    setPlans(current => current.map((p,i) => {
      if(i!==dayIndex) return p;
      const tasks = p.tasks.map((t,j) => j===taskIndex ? {...t,...change} : t);
      return {...p, tasks, totalHours:total(tasks)};
    }));
    setEdited(e => ({...e, [plans[dayIndex].date]:true}));
  }
  const locked = !!busy || recording || fillAttempted;
  return <div className="app">
    <header>
      <div className="brand-group">
        <a className="brand" href="/" onClick={e=>{if(fillAttempted)e.preventDefault();}}>
          <span className="logo">a.</span> ACE <span className="brand-sub">/ daily workspace</span>
        </a>
        {modeSwitch}
      </div>
      <div className="rhythm-badge">
        <span className="sun">↗</span> <strong>09:45 start</strong> <span>9h to under 9h 30m · Contiguous daily rhythm</span>
      </div>
      <div className="steps-compact">
        <span className="active">01 <b>Describe</b></span>
        <span className={plans.length?'active':''}>02 <b>Review</b></span>
        <span className={results?'active':''}>03 <b>Fill in ACE</b></span>
      </div>
    </header>

    <main className="workspace-main">
      {/* LEFT COLUMN: Input controls, notes, and live streaming agent progress */}
      <div className="col-compose">
        <section className="compose panel">
          <div className="section-heading">
            <h2>What did you work on?</h2>
            <div className="switch">
              <button disabled={locked} className={!range?'selected':''} onClick={()=>setRange(false)}>Single day</button>
              <button disabled={locked} className={range?'selected':''} onClick={()=>setRange(true)}>Date range</button>
            </div>
          </div>

          <div className="date-row">
            <label>{range?'From date':'Work date'}
              <input aria-label="Work date" type="date" value={date} disabled={locked} onChange={e=>setDate(e.target.value)}/>
            </label>
            {range && (
              <label>To date
                <input type="date" value={toDate} disabled={locked} onChange={e=>setToDate(e.target.value)}/>
              </label>
            )}
            <span className="date-hint">{range?`${days.length} working days · Sundays skipped`:'India Standard Time (IST)'}</span>
          </div>

          {range && (
            <label className="check">
              <input type="checkbox" checked={perDayMode} disabled={locked} onChange={e=>setPerDayMode(e.target.checked)}/> Use separate notes for each day
            </label>
          )}

          {range && perDayMode ? (
            <div className="per-day">
              {days.map(day=><label key={day}>{day}<textarea disabled={locked} value={perDay[day]||''} onChange={e=>setPerDay({...perDay,[day]:e.target.value})} placeholder="What did you work on this day?"/></label>)}
            </div>
          ) : (
            <>
              <textarea
                className="notes"
                aria-label="Work notes"
                placeholder={'Say or type what you worked on (optional — the assistant also auto-scans your git commits, touched files & created folders for this date)…'}
                value={notes}
                disabled={locked}
                onChange={e=>setNotes(e.target.value)}
                maxLength={20000}
              />
              <div className="compose-footer">
                <button className={'mic '+(recording?'recording':'')} disabled={!!busy || fillAttempted} onClick={startRecording}>
                  <span>{recording?'■':'◉'}</span> {recording?`Stop · ${seconds}s`:'Speak your day'}
                </button>
                <span>English or Hindi · auto-allocates the day</span>
              </div>
            </>
          )}

          {range && !perDayMode && <p className="hint">These notes will be repeated on each working day. Review every date before filling.</p>}

          <div className="plan-action">
            <span>Tasks are <b>New Requirement</b> · Augastam ai</span>
            <div className="plan-buttons">
              <button className="ghost" disabled={locked || ticketLoading} onClick={loadTickets} title="Refresh your assigned tickets from ACE">
                {ticketLoading?'Loading tickets from ACE…':tickets.length?`Tickets loaded (${tickets.length}) · Refresh`:'Retry loading tickets'}
              </button>
              <button
                className="primary"
                disabled={locked || ticketLoading || !date || invalidRange || (perDayMode&&range && days.some(d=>!perDay[d]?.trim()))}
                onClick={buildPlan}
              >
                {isStreamingPlan && !agentRunning?'Planning in progress…':'Create my plan'} <span>↗</span>
              </button>
            </div>
          </div>
          <div className="plan-action agent-action">
            <span>Or let your coding agent read your notes, commits and files</span>
            <div className="plan-buttons">
              <select aria-label="Agent" value={agent} disabled={locked || !agents.length} onChange={e=>setAgent(e.target.value)}>
                {!agents.length && <option value="">No agent set up</option>}
                {agents.map(a => <option key={a.id} value={a.id}>{a.label}</option>)}
              </select>
              <button className="primary" disabled={locked || !agent || !date || invalidRange} onClick={buildWithAgent}
                title={agents.length ? 'Your agent investigates the day and drafts it for review' : 'Run setup_agents.ps1 first'}>
                {agentRunning?'Agent working…':'Draft with agent'} <span>✦</span>
              </button>
            </div>
          </div>
          {noWork.length > 0 && <p className="hint">No work found for {noWork.join(', ')}; dictate the day instead.</p>}
          {skipped.length > 0 && <p className="hint">{skipped.join(' ')}</p>}
        </section>

        {isStreamingPlan && (
          <div className="agent-progress panel" role="status" aria-live="polite">
            <div className="agent-progress-header">
              <div className="agent-status-indicator">
                <span className="agent-pulse" />
                <strong>Assistant Agent Active</strong>
              </div>
              <span className="agent-target-date">
                {range ? `${date} to ${toDate}` : date ? new Date(date + 'T12:00:00').toLocaleDateString('en-IN', {weekday:'short', day:'numeric', month:'short'}) : 'Current Date'}
              </span>
            </div>
            <div className="agent-stream-feed" ref={streamFeedRef}>
              {streamSteps.map((st, i) => {
                const isCurrent = i === streamSteps.length - 1;
                const iconMap = {git:'🌿', commit:'📌', code:'💻', folder:'📁', doc:'📄', ticket:'🎫', notes:'📝', ai:'✨', check:'🔍', done:'✅'};
                return (
                  <div key={i} className={`stream-item ${isCurrent ? 'current' : 'done'}`}>
                    <span className="stream-badge">{isCurrent ? <span className="stream-spinner" /> : iconMap[st.icon] || '✓'}</span>
                    <div className="stream-text">
                      <div className="stream-title-row">
                        <span className="stream-step">{st.step}</span>
                        {st.time && <small className="stream-time">{st.time}</small>}
                      </div>
                      {st.detail && <small className="stream-detail">{st.detail}</small>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {draftNotice && (
          <div className="draft-notice panel" role="status">
            <span>{draftNotice.text}</span>
            <button className="primary" disabled={!!busy || fillAttempted} onClick={() => loadDraft(draftNotice)}>Load</button>
            <button className="ghost" onClick={() => {markSeen(draftNotice.draft.date, draftNotice.createdAt); setDraftNotice(null);}}>Dismiss</button>
          </div>
        )}
        {error && <div role="alert" className="error">{error}</div>}
        {health && Object.entries(health.providers).some(([,ready])=>!ready) && (
          <p className="warning">Configure missing provider keys in .env: {Object.entries(health.providers).filter(([,ready])=>!ready).map(([name])=>name).join(', ')}.</p>
        )}
      </div>

      {/* RIGHT COLUMN: Review Pane & Draft Handoff */}
      <div className="col-review">
        {plans.length === 0 && !results && !isStreamingPlan && (
          <div className="standby panel">
            <div className="standby-icon">📋</div>
            <h3>Ready to plan your timesheet</h3>
            <p>Pick a date on the left and click <b>Create my plan</b>. You can leave notes completely empty — the assistant will automatically scan your machine for git commits, touched files, and newly created folders for that day.</p>
            <div className="standby-tips">
              <span className="tip-badge">Pro-tip</span>
              <small>Tasks are formatted with ticket IDs and contiguous time intervals totaling 9h to under 9h 30m.</small>
            </div>
          </div>
        )}

        {plans.length === 0 && isStreamingPlan && (
          <div className="standby panel planning-standby">
            <div className="standby-spinner" />
            <h3>Analyzing your activity & generating plan…</h3>
            <p>Inspecting local git repositories, document changes, and ACE tickets in real time. Watch the live progress on the left.</p>
          </div>
        )}

        {!!plans.length && (
          <section className="preview">
            <div className="preview-top-bar">
              <div>
                <span className="eyebrow">MAKE IT YOURS</span>
                <h2>Review your plan</h2>
              </div>
              <span className="pill">{plans.reduce((n,p)=>n+p.tasks.length,0)} tasks · {plans.length} {plans.length===1?'day':'days'}</span>
            </div>

            {streamSteps.length > 0 && (
              <div className="stream-audit-toggle">
                <button className="stream-toggle-btn" onClick={() => setShowSteps(s => !s)}>
                  {showSteps ? '▲ Hide agent activity log' : `▼ View agent activity log (${streamSteps.length} events parsed)`}
                </button>
                {showSteps && (
                  <div className="agent-stream-feed audit">
                    {streamSteps.map((st, i) => {
                      const iconMap = {git:'🌿', commit:'📌', code:'💻', folder:'📁', doc:'📄', ticket:'🎫', notes:'📝', ai:'✨', check:'🔍', done:'✅'};
                      return (
                        <div key={i} className="stream-item done">
                          <span className="stream-badge">{iconMap[st.icon] || '✓'}</span>
                          <div className="stream-text">
                            <div className="stream-title-row">
                              <span className="stream-step">{st.step}</span>
                              {st.time && <small className="stream-time">{st.time}</small>}
                            </div>
                            {st.detail && <small className="stream-detail">{st.detail}</small>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <div className="plans-scroll-area">
              {plans.map((p,di)=>(
                <article className="day panel" key={p.date}>
                  <div className="day-heading">
                    <h3>{new Date(p.date+'T12:00:00').toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</h3>
                    <span>{p.workplace} <b>·</b> {p.totalHours} hours</span>
                  </div>
                  {p.activitySummary && <div className="activity-badge">🔍 {p.activitySummary}</div>}
                  {p.warnings.map((w,i)=><p className="warning" key={i}>{w}</p>)}
                  {p.tasks.map((t,ti)=>(
                    <div className="task" key={ti}>
                      <span className="task-number">{String(ti+1).padStart(2,'0')}</span>
                      <div className="task-body">
                        <div className="task-header-row">
                          <div className="task-meta">
                            <span>NEW REQUIREMENT</span>
                            <span>Augastam ai</span>
                          </div>
                          <div className="task-inline-times">
                            <label>From <input aria-label={`Start ${di+1}.${ti+1}`} type="time" value={t.start} disabled={!!busy||fillAttempted} onChange={e=>updateTask(di,ti,{start:e.target.value})}/></label>
                            <span className="time-arrow">→</span>
                            <label>To <input aria-label={`End ${di+1}.${ti+1}`} type="time" value={t.end} disabled={!!busy||fillAttempted} onChange={e=>updateTask(di,ti,{end:e.target.value})}/></label>
                          </div>
                        </div>
                        <textarea
                          aria-label={`Description ${di+1}.${ti+1}`}
                          value={t.description}
                          maxLength={500}
                          disabled={!!busy||fillAttempted}
                          onChange={e=>updateTask(di,ti,{description:e.target.value})}
                        />
                        <div className="task-bottom">
                          <label>Ticket
                            <select aria-label={`Ticket ${di+1}.${ti+1}`} disabled={!!busy||fillAttempted} value={t.ticket||''} onChange={e=>updateTask(di,ti,tagTask(t,e.target.value))}>
                              <option value="">No ticket</option>
                              {[...new Set([...(t.ticket?[t.ticket]:[]),...tickets.map(x=>x.ticket)])].map(number=><option key={number}>{number}</option>)}
                            </select>
                          </label>
                          <span className="counter">{t.description.length}/500</span>
                        </div>
                        {t.matchReason && <small className="match-reason">{t.matchReason}</small>}
                        {t.evidence && <small className="evidence">Based on: {t.evidence}</small>}
                      </div>
                    </div>
                  ))}
                </article>
              ))}
            </div>

            {issues.length>0 && <div className="error" role="alert">{issues.map(i=><p key={i}>{i}</p>)}</div>}
            {adjustableDays.length>0 && <button className="ghost" disabled={!!busy} onClick={() => {
              setPlans(current => current.map(adjustLongDay)); setEdited(e => ({...e, ...Object.fromEntries(adjustableDays.map(p => [p.date, true]))}));
              setConfirmed(false);
            }}>Adjust {adjustableDays.length} overlong {adjustableDays.length===1?'day':'days'} to 9h 15m</button>}

            <div className="fill-bar panel">
              <div>
                <label className="check">
                  <input type="checkbox" checked={confirmed} disabled={!!busy} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed the tasks, dates, tickets, and time allocation.
                </label>
                <small>Fills every row into ACE draft and stops. Review and Save in ACE browser.</small>
              </div>
              <button
                className="primary"
                disabled={!!busy||issues.length>0||!confirmed}
                onClick={fillPlans}
              >
                {busy.includes('Filling')?busy:(results?.days?.length&&results.days.every(d=>d.status==='filled'))?'Re-verify ACE draft ↗':fillAttempted?'Resume fill ↗':'Fill in ACE ↗'}
              </button>
            </div>
          </section>
        )}

        {results && (
          <section className="panel result" aria-live="polite">
            <h2>Portal handoff</h2>
            {results.days.map(day=>{
              const saved = savedDays[day.date]?.status === 'filled';
              const meta=saved ? {cls:'ok',label:'Saved in ACE ✓'} : {filled:{cls:'skip',label:'Draft filled — waiting for ACE Save'},skipped:{cls:'skip',label:'Skipped — this date already has entries'},interrupted:{cls:'bad',label:'Needs review — this date was not filled'}}[day.status]||{cls:'',label:day.status};
              return (
                <article className={'result-day '+meta.cls} key={day.date}>
                  <div className="result-head">
                    <strong>{new Date(day.date+'T12:00:00').toLocaleDateString('en-IN',{weekday:'long',day:'numeric',month:'long',year:'numeric'})}</strong>
                    <span className={'result-badge '+meta.cls}>{meta.label}</span>
                  </div>
                  <p>{saved ? savedDays[day.date].reason : day.message}</p>
                  {day.status==='skipped'&&day.gridRows.length>0&&(
                    <div className="existing">
                      <small>This date already has {day.gridRows.length} {day.gridRows.length===1?'entry':'entries'} in ACE, left untouched:</small>
                      <ol>{day.gridRows.map((r,i)=><li key={i}><span className="ex-time">{r.start}–{r.end}</span> {r.description}</li>)}</ol>
                      <small>To let the assistant fill this date, remove these in the ACE portal first, then run it again.</small>
                    </div>
                  )}
                  {day.status==='filled'&&!saved&&(
                    <>
                      <div className="fill-action-box">
                        <div>
                          <strong>✅ Tasks successfully placed in ACE draft!</strong>
                          <p>Switch to your open ACE browser window, review the entries in the grid, and click the blue <b>Save</b> button to finalize.</p>
                        </div>
                      </div>
                      <small>{day.gridRows.length} {day.gridRows.length===1?'row':'rows'} filled, not saved — review and click Save in ACE.</small>
                    </>
                  )}
                  {day.screenshotUrl&&(
                    <div><a className="screenshot-link" href={day.screenshotUrl} target="_blank" rel="noreferrer">📸 View filled grid screenshot proof ↗</a></div>
                  )}
                </article>
              );
            })}
            {results.notStarted.length>0&&<p className="warning">Not started: {results.notStarted.join(', ')}</p>}
            <p className="warning">Keep the backend and ACE tabs open until you have saved each day. Nothing has been submitted by this app.</p>
          </section>
        )}
      </div>
    </main>

    {busy && <div role="status" className="status"><span className="spinner"/>{busy}</div>}
    <footer>
      <span>ACE TIMESHEET ASSISTANT</span>
      <span>Daily total: 9h to under 9h 30m</span>
      <span>Your review. Your final say.</span>
    </footer>
  </div>;
}

const MODES = [['dashboard','Dashboard'], ['timesheet','Timesheet'], ['ideas','Ticket ideas'], ['tasks','Create tasks']];

function Root() {
  // The dashboard is the landing page every time the app opens.
  const [mode, setMode] = useState('dashboard');
  const [jump, setJump] = useState(null);
  const [ideaNotes, setIdeaNotes] = useState(null);
  // All screens stay mounted so switching never discards a plan or an open fill.
  const modeSwitch = <div className="switch mode-switch" role="tablist" aria-label="Workspace">
    {MODES.map(([key, label]) => <button key={key} role="tab" aria-selected={mode===key}
      className={mode===key?'selected':''} onClick={()=>setMode(key)}>{label}</button>)}
  </div>;
  const fillDay = date => {setJump({date, at: Date.now()}); setMode('timesheet');};
  const draftIdeas = notes => {setIdeaNotes({notes, at: Date.now()}); setMode('tasks');};
  return <>
    <div hidden={mode!=='dashboard'}><Dashboard modeSwitch={modeSwitch} onFillDay={fillDay}/></div>
    <div hidden={mode!=='timesheet'}><App modeSwitch={modeSwitch} jump={jump}/></div>
    <div hidden={mode!=='ideas'}><TicketIdeas modeSwitch={modeSwitch} onDraft={draftIdeas}/></div>
    <div hidden={mode!=='tasks'}><TaskApp modeSwitch={modeSwitch} ideaNotes={ideaNotes}/></div>
  </>;
}

createRoot(document.getElementById('root')).render(<Root/>);

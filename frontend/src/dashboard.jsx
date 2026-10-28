import React, {useEffect, useState} from 'react';
import {api, streamEvents} from './api';
import {STATUS, leadingBlanks, pendingDays, progress, shiftMonth} from './status';

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const TILES = ['filled', 'partial', 'missing', 'failed', 'unchecked'];

const longDate = iso => new Date(iso + 'T12:00:00').toLocaleDateString('en-IN', {weekday:'short', day:'numeric', month:'short'});
const monthName = month => new Date(month + '-01T12:00:00').toLocaleDateString('en-IN', {month:'long', year:'numeric'});
const checkedTime = iso => new Date(iso).toLocaleString('en-IN', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'});

export function Dashboard({modeSwitch, onFillDay}) {
  const [thisMonth, setThisMonth] = useState('');
  const [month, setMonth] = useState('');
  const [status, setStatus] = useState(null);
  const [selected, setSelected] = useState(null);
  const [scan, setScan] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/health').then(h => {const m = h.today.slice(0, 7); setThisMonth(m); setMonth(m);}).catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    if (!month) return;
    setSelected(null);
    api('/status?month=' + month).then(setStatus).catch(e => setError(e.message));
    const timer = setInterval(() => {
      if (!document.hidden) api('/status?month=' + month).then(setStatus).catch(() => {});
    }, 15000);
    return () => clearInterval(timer);
  }, [month]);

  async function checkAce(full) {
    setError(''); setScan({step:'Opening ACE…', detail:null});
    try {
      const result = await streamEvents('/status/refresh-stream', {month, full}, s => setScan(s), 'Could not start the ACE check.');
      if (result?.status) setStatus(result.status);
      if (result && !result.checked) setError('Everything this month is already up to date. Use “Rescan whole month” to check every day again.');
    } catch (e) {
      setError(e.message);
      api('/status?month=' + month).then(setStatus).catch(() => {});
    } finally {
      setScan(null);
    }
  }

  async function toggleLeave(day) {
    setError('');
    try {
      setStatus(await api('/status/leave', {day:day.date, leave:day.status !== 'leave'}));
      setSelected(null);
    } catch (e) {setError(e.message);}
  }

  const days = status?.days || [];
  const pending = pendingDays(days);
  const pick = selected && days.find(d => d.date === selected);
  const busy = !!scan;

  return <div className="app">
    <header>
      <div className="brand-group">
        <a className="brand" href="/"><span className="logo">a.</span> ACE <span className="brand-sub">/ daily workspace</span></a>
        {modeSwitch}
      </div>
      <div className="dash-checked">
        {status?.lastChecked ? <>Last checked in ACE <b>{checkedTime(status.lastChecked)}</b></> : 'Not checked in ACE yet'}
      </div>
    </header>

    <main className="dash">
      <section className="panel dash-summary">
        <div className="dash-title">
          <div>
            <h2>{month ? monthName(month) : 'Loading…'}</h2>
            <p>{status ? `${status.counts.filled} of ${status.workingDays - status.counts.leave} working days filled so far` : ''}</p>
          </div>
          <div className="dash-actions">
            <button className="ghost" disabled={busy || !status} onClick={() => checkAce(true)}
              title="Opens ACE and re-reads every working day this month">Rescan whole month</button>
            <button className="primary" disabled={busy || !status} onClick={() => checkAce(false)}
              title="Opens ACE and reads Date of Report for new, pending and recent days">{busy ? 'Checking…' : 'Check ACE'}</button>
          </div>
        </div>
        {status && <>
          <div className="dash-bar" role="progressbar" aria-valuenow={progress(status)} aria-valuemin="0" aria-valuemax="100">
            <i style={{width: progress(status) + '%'}}/>
          </div>
          <div className="dash-tiles">
            {TILES.map(k => <div key={k} className={'dash-tile s-' + k}>
              <b>{status.counts[k]}</b><span>{STATUS[k].label}</span><small>{STATUS[k].hint}</small>
            </div>)}
          </div>
        </>}
        {scan && <p className="dash-scan"><span className="stream-spinner"/> {scan.step}{scan.detail ? ` · ${scan.detail}` : ''}</p>}
        {error && <div role="alert" className="error">{error}</div>}
      </section>

      <div className="dash-grid">
        <section className="panel dash-calendar">
          <div className="dash-cal-head">
            <button className="ghost" disabled={busy} onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Previous month">‹</button>
            <h3>{month && monthName(month)}</h3>
            <button className="ghost" disabled={busy || month >= thisMonth} onClick={() => setMonth(shiftMonth(month, 1))} aria-label="Next month">›</button>
          </div>
          <div className="dash-cal">
            {WEEKDAYS.map(w => <div key={w} className="dash-wd">{w}</div>)}
            {month && Array.from({length: leadingBlanks(month)}, (_, i) => <div key={'b' + i}/>)}
            {days.map(d => {
              const open = !['weekend', 'future'].includes(d.status);
              return <button key={d.date} disabled={!open}
                className={'dash-day s-' + d.status + (selected === d.date ? ' picked' : '')}
                title={d.reason} onClick={() => setSelected(d.date)}>
                <b>{Number(d.date.slice(8))}</b>
                {d.savedHours && <small>{d.savedHours}</small>}
              </button>;
            })}
          </div>
          <div className="dash-legend">
            {Object.entries(STATUS).map(([k, v]) => <span key={k}><i className={'s-' + k}/>{v.label}</span>)}
          </div>
        </section>

        <aside className="dash-side">
          {pick && <section className={'panel dash-detail s-' + pick.status}>
            <h3>{longDate(pick.date)}</h3>
            <p className="dash-badge">{STATUS[pick.status]?.label}</p>
            <p>{pick.reason}</p>
            {pick.checkedAt && <small>Checked {checkedTime(pick.checkedAt)}</small>}
            <div className="dash-actions">
              {pick.status !== 'leave' && pick.status !== 'filled' &&
                <button className="primary" onClick={() => onFillDay(pick.date)}>Fill this day</button>}
              <button className="ghost" disabled={busy} onClick={() => toggleLeave(pick)}>
                {pick.status === 'leave' ? 'Undo leave' : 'Mark as leave'}</button>
            </div>
          </section>}

          <section className="panel dash-pending">
            <h3>Pending, oldest first</h3>
            {!status ? <p className="dash-muted">Loading…</p>
              : pending.length === 0
                ? <p className="dash-muted">{status.counts.unchecked ? 'Nothing pending among the days checked so far. Run Check ACE for the rest.' : 'All caught up for this month.'}</p>
                : pending.map(d => <div key={d.date} className={'dash-row s-' + d.status}>
                  <div><b>{longDate(d.date)}</b><span>{d.reason}</span></div>
                  <button className="ghost" onClick={() => onFillDay(d.date)}>Fill</button>
                </div>)}
          </section>
        </aside>
      </div>
    </main>
  </div>;
}

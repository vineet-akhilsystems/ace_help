import React, {useEffect, useState} from 'react';
import {api} from './api';
import {ideaNotes} from './plan';

export function TicketIdeas({modeSwitch, onDraft}) {
  const [toDate, setToDate] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [ideas, setIdeas] = useState(null);
  const [selected, setSelected] = useState([]);
  const [manualNotes, setManualNotes] = useState('');
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api('/health').then(h => {
      setToDate(h.today);
      setFromDate(h.today);
    }).catch(e => setError(e.message));
  }, []);

  async function scan() {
    setBusy(true); setError(''); setIdeas(null); setSelected([]);
    try {
      const result = await api('/ticket-ideas', {fromDate, toDate});
      setIdeas(result);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const toggle = index => setSelected(current =>
    current.includes(index) ? current.filter(i => i !== index) : [...current, index]);
  const shown = ideas ? ideas.ideas.map((item, i) => ({item, i})).filter(({item}) =>
    !query || (item.date + ' ' + item.repo + ' ' + item.title + ' ' + item.evidence.join(' ')).toLowerCase().includes(query.toLowerCase())) : [];
  const open = shown.filter(({item}) => !item.ticket);
  // Select all skips work that already names a ticket.
  const selectAll = () => setSelected(current => [...new Set([...current, ...open.map(({i}) => i)])]);
  const draft = () => onDraft(ideaNotes(selected.map(i => ideas.ideas[i]), manualNotes));

  return <div className="app">
    <header><div className="brand-group">
      <span className="brand"><span className="logo">a.</span> ACE <span className="brand-sub">/ ticket ideas</span></span>
      {modeSwitch}
    </div></header>
    <main className="dash">
      <section className="panel dash-summary">
        <h2>Find work that may need tickets</h2>
        <p>See local code changes, new files and folders, repositories, documents and commits for each day. Review the activity and choose work that needs a ticket.</p>
        <div className="idea-controls">
          <label>From <input aria-label="Idea scan from date" type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}/></label>
          <label>To <input aria-label="Idea scan to date" type="date" value={toDate} onChange={e => setToDate(e.target.value)}/></label>
          <button className="primary" disabled={busy || !fromDate || !toDate} onClick={scan}>
            {busy ? 'Scanning activity…' : 'Find ticket ideas'}
          </button>
        </div>
        <small>Scan up to 31 days at a time. You can repeat the scan for older months.</small>
        <label className="idea-notes">Work the scan may miss
          <textarea value={manualNotes} maxLength={10000} onChange={e => setManualNotes(e.target.value)}
            placeholder="Add meetings, investigations, support work, or other tasks you did without a commit."/>
        </label>
        {error && <div role="alert" className="error">{error}</div>}
      </section>
      {ideas && <section className="panel dash-summary">
        <h2>{ideas.total} activity {ideas.total === 1 ? 'item' : 'items'}</h2>
        <p>{ideas.note}</p>
        {ideas.truncated && <p className="warning">Showing the first {ideas.ideas.length} items. Narrow the date range to see more.</p>}
        <input className="idea-search" aria-label="Filter activity" placeholder="Filter by date, project or file" value={query}
          onChange={e => setQuery(e.target.value)}/>
        <div className="idea-controls">
          <button className="ghost" disabled={!open.length} onClick={selectAll}>Select all shown ({open.length})</button>
          <button className="ghost" disabled={!selected.length} onClick={() => setSelected([])}>Clear</button>
          <small>{selected.length} selected · items that already name a ticket are left out</small>
        </div>
        <div className="idea-list">
          {shown.map(({item, i}) => <label className="idea-row" key={i}>
            <input type="checkbox" checked={selected.includes(i)} onChange={() => toggle(i)}/>
            <span><b>{item.title}</b>{item.ticket && <em className="pill">Has ticket {item.ticket}</em>}
              <small>{item.date} · {item.kind} · {item.evidence.join(' · ')}</small></span>
          </label>)}
        </div>
        <button className="primary" disabled={!selected.length && !manualNotes.trim()} onClick={draft}>
          Create tickets for {selected.length} selected {selected.length === 1 ? 'item' : 'items'} ↗
        </button>
        <small>Your agent groups these into one ticket per piece of work, each assigned to you. You review every ticket before it goes into ACE.</small>
      </section>}
    </main>
  </div>;
}

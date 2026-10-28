import React, {useEffect, useState} from 'react';
import {api} from './api';

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
      setFromDate(h.today.slice(0, 7) + '-01');
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
  const draft = () => {
    const notes = selected.slice(0, 30).map(i => {
      const item = ideas.ideas[i];
      return item.date + ': ' + item.title + ' (' + item.kind + (item.repo ? ', ' + item.repo : '') + '). Evidence: ' + item.evidence.join(', ') + '.';
    }).concat(manualNotes.trim() ? [manualNotes.trim()] : []).join('\n').slice(0, 20000);
    onDraft(notes);
  };

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
        <div className="idea-list">
          {ideas.ideas.map((item, i) => ({item, i})).filter(({item}) =>
            !query || (item.date + ' ' + item.repo + ' ' + item.title + ' ' + item.evidence.join(' ')).toLowerCase().includes(query.toLowerCase())
          ).map(({item, i}) => <label className="idea-row" key={i}>
            <input type="checkbox" checked={selected.includes(i)} onChange={() => toggle(i)}/>
            <span><b>{item.title}</b><small>{item.date} · {item.kind} · {item.evidence.join(' · ')}</small></span>
          </label>)}
        </div>
        <button className="primary" disabled={!selected.length && !manualNotes.trim()} onClick={draft}>
          Draft tickets from {Math.min(selected.length, 30)} selected ideas
        </button>
        {selected.length > 30 && <small>Draft the first 30 selected ideas, then return for the rest.</small>}
      </section>}
    </main>
  </div>;
}

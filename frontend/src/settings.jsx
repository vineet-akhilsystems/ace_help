import React, {useState} from 'react';
import {api} from './api';

export function LoginSetup({status, onSaved, onCancel}) {
  const [username, setUsername] = useState(status.username || '');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(status.restartRequired);
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await api('/settings/credentials', {username: username.trim(), password});
      setPassword(''); setShowPassword(false); setSaved(true); onSaved();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  return <main className="login-setup">
    <section className="panel login-card" aria-labelledby="login-title">
      <span className="brand"><span className="logo">a.</span> ACE</span>
      <h1 id="login-title">{status.configured ? 'ACE login settings' : 'Set up your ACE login'}</h1>
      <p>Enter the username and password you use to sign in to the ACE portal.</p>
      {saved ? <div role="status">
        <h2>Login saved</h2>
        <p>Close the assistant terminal and run <code>start.ps1</code> again, then reload this page.</p>
        <p>Your next ACE action will use the new login. Credentials have not been verified with ACE yet.</p>
      </div> : <form onSubmit={save}>
        <label className="tf"><span>ACE username</span>
          <input name="username" autoComplete="username" required maxLength={120} value={username}
            disabled={busy} onChange={e => setUsername(e.target.value)}/>
        </label>
        <label className="tf"><span>ACE password</span>
          <input name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password"
            required maxLength={512} value={password} disabled={busy} onChange={e => setPassword(e.target.value)}/>
        </label>
        <label className="check"><input type="checkbox" checked={showPassword}
          onChange={e => setShowPassword(e.target.checked)}/> Show password</label>
        <p className="muted">Saved on this computer in the local .env file as plain text. The password is never displayed again by the app.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="login-actions">
          {onCancel && <button type="button" className="ghost" disabled={busy} onClick={onCancel}>Back</button>}
          <button className="primary" disabled={busy || !username.trim() || !password}>
            {busy ? 'Saving...' : 'Save ACE login'}
          </button>
        </div>
      </form>}
    </section>
  </main>;
}

import { useState } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';

export default function WatchlistEditor() {
  const { watchlist, loading, add, remove } = useWatchlist();
  const [ticker, setTicker] = useState('');
  const [name,   setName]   = useState('');
  const [busy,   setBusy]   = useState(false);
  const [err,    setErr]    = useState('');

  async function handleAdd(e) {
    e.preventDefault();
    if (!ticker.trim()) return;
    setBusy(true); setErr('');
    try {
      await add(ticker.trim(), name.trim() || undefined);
      setTicker(''); setName('');
    } catch {
      setErr('Failed to add ticker.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={handleAdd} style={styles.form}>
        <input
          style={styles.input}
          placeholder="TICKER"
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          maxLength={10}
        />
        <input
          style={styles.input}
          placeholder="Company name (optional)"
          value={name}
          onChange={e => setName(e.target.value)}
        />
        <button style={styles.btn} type="submit" disabled={busy || !ticker.trim()}>
          Add
        </button>
      </form>
      {err && <p style={styles.err}>{err}</p>}

      {loading ? <p style={styles.hint}>Loading...</p> : (
        <ul style={styles.list}>
          {watchlist.map(w => (
            <li key={w.ticker} style={styles.item}>
              <span style={styles.ticker}>{w.ticker}</span>
              {w.name && <span style={styles.name}>{w.name}</span>}
              <button
                style={styles.remove}
                onClick={() => remove(w.ticker)}
                title="Remove"
              >
                &times;
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const styles = {
  form:   { display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' },
  input:  { flex: 1, minWidth: 100, padding: '8px 12px', borderRadius: 6, border: '1px solid #334155', background: '#0f172a', color: '#f8fafc', fontSize: 14 },
  btn:    { padding: '8px 18px', borderRadius: 6, border: 'none', background: '#3b82f6', color: '#fff', cursor: 'pointer', fontWeight: 600 },
  err:    { color: '#f87171', fontSize: 13, marginBottom: 8 },
  hint:   { color: '#64748b', fontSize: 13 },
  list:   { listStyle: 'none', padding: 0, margin: 0 },
  item:   { display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid #1e293b' },
  ticker: { fontWeight: 700, color: '#f8fafc', minWidth: 60 },
  name:   { color: '#94a3b8', fontSize: 13, flex: 1 },
  remove: { background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 18, lineHeight: 1 },
};

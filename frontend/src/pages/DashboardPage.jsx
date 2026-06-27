import { useState } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';
import { triggerIngest } from '../api/marketApi';
import SignalFeed from '../components/SignalFeed';

export default function DashboardPage() {
  const { watchlist } = useWatchlist();
  const [selected, setSelected]   = useState(null);
  const [ingesting, setIngesting] = useState(false);
  const [status, setStatus]       = useState('');

  async function handleIngest() {
    setIngesting(true); setStatus('');
    try {
      const r = await triggerIngest();
      setStatus(r.status === 'triggered' ? 'Ingest triggered.' : `Status: ${r.status}`);
    } catch {
      setStatus('Could not reach Python agent.');
    } finally {
      setIngesting(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.toolbar}>
        <h1 style={styles.title}>Signal Dashboard</h1>
        <button style={styles.btn} onClick={handleIngest} disabled={ingesting}>
          {ingesting ? 'Triggering...' : 'Ingest Now'}
        </button>
      </div>
      {status && <p style={styles.status}>{status}</p>}

      <div style={styles.filters}>
        <button
          style={selected === null ? styles.filterActive : styles.filter}
          onClick={() => setSelected(null)}
        >
          All
        </button>
        {watchlist.map(w => (
          <button
            key={w.ticker}
            style={selected === w.ticker ? styles.filterActive : styles.filter}
            onClick={() => setSelected(w.ticker)}
          >
            {w.ticker}
          </button>
        ))}
      </div>

      <SignalFeed ticker={selected} />
    </div>
  );
}

const styles = {
  page:        { maxWidth: 800, margin: '0 auto', padding: '32px 16px' },
  toolbar:     { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  title:       { color: '#f8fafc', fontSize: 24, fontWeight: 700, margin: 0 },
  btn:         { padding: '8px 18px', borderRadius: 6, border: 'none', background: '#3b82f6', color: '#fff', cursor: 'pointer', fontWeight: 600 },
  status:      { color: '#94a3b8', fontSize: 13, marginBottom: 12 },
  filters:     { display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 },
  filter:      { padding: '4px 14px', borderRadius: 20, border: '1px solid #334155', background: 'transparent', color: '#94a3b8', cursor: 'pointer', fontSize: 13 },
  filterActive:{ padding: '4px 14px', borderRadius: 20, border: '1px solid #3b82f6', background: '#1e3a5f', color: '#93c5fd', cursor: 'pointer', fontSize: 13 },
};

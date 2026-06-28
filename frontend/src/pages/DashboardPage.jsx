import { useState, useEffect } from 'react';
import { useWatchlist } from '../hooks/useWatchlist';
import { triggerIngest, getPrices, getSignals } from '../api/marketApi';
import SignalFeed     from '../components/SignalFeed';
import SentimentChart from '../components/SentimentChart';

export default function DashboardPage() {
  const { watchlist } = useWatchlist();
  const [selected,   setSelected]   = useState(null);
  const [ingesting,  setIngesting]  = useState(false);
  const [status,     setStatus]     = useState('');
  const [chartData,  setChartData]  = useState([]);

  useEffect(() => {
    if (!selected) { setChartData([]); return; }

    Promise.all([
      getPrices(selected, 30),
      getSignals(selected, 50),
    ]).then(([prices, signals]) => {
      const rows = prices.map(p => ({
        date:       p.date,
        price:      p.close ? Number(p.close) : null,
        confidence: null,
        sentiment:  null,
      }));

      // Snap each signal to the nearest earlier (or equal) price date
      for (const s of signals) {
        const sigDate = s.publishedAt?.slice(0, 10);
        if (!sigDate) continue;
        const idx = rows.reduce((best, r, i) =>
          r.date <= sigDate && (best === -1 || r.date > rows[best].date) ? i : best, -1);
        if (idx !== -1 && (!rows[idx].confidence || s.confidence > rows[idx].confidence)) {
          rows[idx].confidence = s.confidence;
          rows[idx].sentiment  = s.sentiment;
        }
      }

      setChartData(rows);
    }).catch(() => setChartData([]));
  }, [selected]);

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

      {selected && chartData.length > 0 && (
        <SentimentChart
          data={chartData}
          ticker={selected}
          name={watchlist.find(w => w.ticker === selected)?.name}
        />
      )}

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

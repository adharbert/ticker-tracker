import { useState, useEffect } from 'react';
import { getBacktest } from '../api/marketApi';

const DISCLAIMER = "BACKTESTING NOTICE: Historical correlation between signals and price moves does not predict future performance. This is an evaluation tool only.";

export default function BacktestPage() {
  const [results,  setResults]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState('');

  useEffect(() => {
    getBacktest()
      .then(data => setResults(Array.isArray(data) ? data : [data]))
      .catch(() => setError('No backtest data yet. Run: python -m scripts.backtest'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div style={styles.page}><p style={styles.muted}>Loading...</p></div>;

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Backtest Results</h1>
      <p style={styles.disclaimer}>{DISCLAIMER}</p>

      {error && <p style={styles.error}>{error}</p>}

      {results.length === 0 && !error && (
        <p style={styles.muted}>
          No results yet. Run <code>python -m scripts.backtest</code> from the python-agent directory.
        </p>
      )}

      <div style={styles.grid}>
        {results.map(r => (
          <ResultCard key={r.ticker} result={r} />
        ))}
      </div>

      {results.length > 0 && (
        <p style={styles.runNote}>
          Results computed at {new Date(results[0].computedAt).toLocaleString()}. Re-run after accumulating more signals.
        </p>
      )}
    </div>
  );
}

function ResultCard({ result: r }) {
  const hasAccuracy = r.accuracy != null;
  const pct         = hasAccuracy ? `${(r.accuracy * 100).toFixed(1)}%` : null;
  const baseline    = `${(r.baselineAccuracy * 100).toFixed(0)}%`;
  const delta       = r.vsBaseline != null ? r.vsBaseline * 100 : null;
  const deltaColor  = delta == null ? '#64748b' : delta > 0 ? '#10b981' : '#ef4444';

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <span style={styles.ticker}>{r.ticker}</span>
        <span style={styles.sampleBadge}>{r.sampleSize} signals · {r.lookAheadDays}d look-ahead</span>
      </div>

      {hasAccuracy ? (
        <div style={styles.accuracy}>
          <div style={styles.accuracyMain}>
            <span style={styles.accuracyValue}>{pct}</span>
            <span style={styles.accuracyLabel}>accuracy</span>
          </div>
          <div style={styles.baseline}>
            <span style={{ color: '#64748b', fontSize: '0.8rem' }}>vs {baseline} baseline</span>
            <span style={{ color: deltaColor, fontWeight: 700, fontSize: '0.9rem', marginLeft: 6 }}>
              {delta != null ? `${delta > 0 ? '+' : ''}${delta.toFixed(1)}%` : '—'}
            </span>
          </div>
          <AccuracyBar accuracy={r.accuracy} />
        </div>
      ) : (
        <div style={styles.hidden}>
          <span style={styles.hiddenIcon}>🔒</span>
          <span style={styles.hiddenText}>{r.accuracyNote || 'Insufficient data'}</span>
        </div>
      )}
    </div>
  );
}

function AccuracyBar({ accuracy }) {
  const pct      = accuracy * 100;
  const color    = pct >= 55 ? '#10b981' : pct >= 45 ? '#f59e0b' : '#ef4444';
  return (
    <div style={styles.barTrack}>
      <div style={{ ...styles.barFill, width: `${pct}%`, background: color }} />
      <div style={styles.barBaseline} />
    </div>
  );
}

const styles = {
  page:         { maxWidth: 900, margin: '0 auto', padding: '32px 16px' },
  title:        { color: '#f8fafc', fontSize: 24, fontWeight: 700, marginBottom: 8 },
  disclaimer:   { color: '#f59e0b', fontSize: 12, background: '#1c1a10', border: '1px solid #854d0e', borderRadius: 6, padding: '8px 12px', marginBottom: 24 },
  error:        { color: '#f87171', fontSize: 14, marginBottom: 16 },
  muted:        { color: '#64748b', fontSize: 14 },
  runNote:      { color: '#475569', fontSize: 12, marginTop: 24 },
  grid:         { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 },
  card:         { background: '#1e293b', borderRadius: 10, padding: '16px 18px', border: '1px solid #334155' },
  cardHeader:   { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  ticker:       { color: '#f8fafc', fontWeight: 700, fontSize: '1.1rem' },
  sampleBadge:  { color: '#64748b', fontSize: '0.75rem' },
  accuracy:     { display: 'flex', flexDirection: 'column', gap: 4 },
  accuracyMain: { display: 'flex', alignItems: 'baseline', gap: 8 },
  accuracyValue:{ color: '#f8fafc', fontSize: '2rem', fontWeight: 700 },
  accuracyLabel:{ color: '#94a3b8', fontSize: '0.8rem' },
  baseline:     { display: 'flex', alignItems: 'center', marginBottom: 8 },
  barTrack:     { position: 'relative', height: 8, background: '#0f172a', borderRadius: 4, overflow: 'visible' },
  barFill:      { height: '100%', borderRadius: 4, transition: 'width 0.4s ease' },
  barBaseline:  { position: 'absolute', top: -2, left: '50%', width: 2, height: 12, background: '#475569', borderRadius: 1 },
  hidden:       { display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 0' },
  hiddenIcon:   { fontSize: '1.2rem' },
  hiddenText:   { color: '#94a3b8', fontSize: '0.82rem', lineHeight: 1.4 },
};

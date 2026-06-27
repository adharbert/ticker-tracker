import GovernanceBadge from './GovernanceBadge';

const SENTIMENT_COLOR = {
  bullish: '#16a34a',
  bearish: '#dc2626',
  neutral: '#6b7280',
};

export default function SignalCard({ signal }) {
  const { ticker, eventType, sentiment, confidence, impactSummary, timeHorizon,
          sourceCitations, uncertaintyFactors, publishedAt } = signal;

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <span style={styles.ticker}>{ticker}</span>
        <span style={{ ...styles.sentiment, color: SENTIMENT_COLOR[sentiment] ?? '#6b7280' }}>
          {sentiment}
        </span>
        <span style={styles.event}>{eventType}</span>
        <span style={styles.confidence}>{(confidence * 100).toFixed(0)}%</span>
      </div>

      <p style={styles.summary}>{impactSummary}</p>

      {uncertaintyFactors?.length > 0 && (
        <ul style={styles.list}>
          {uncertaintyFactors.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      )}

      <div style={styles.footer}>
        <span style={styles.meta}>Horizon: {timeHorizon}</span>
        {sourceCitations?.length > 0 && (
          <span style={styles.meta}>{sourceCitations.length} source{sourceCitations.length > 1 ? 's' : ''}</span>
        )}
        <span style={styles.meta}>{new Date(publishedAt).toLocaleDateString()}</span>
      </div>

      <div style={{ marginTop: 8 }}>
        <GovernanceBadge />
      </div>
    </div>
  );
}

const styles = {
  card:       { background: '#1e293b', borderRadius: 8, padding: '16px', marginBottom: 12 },
  header:     { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' },
  ticker:     { fontWeight: '700', fontSize: '16px', color: '#f8fafc' },
  sentiment:  { fontWeight: '600', textTransform: 'capitalize' },
  event:      { color: '#94a3b8', fontSize: '13px', textTransform: 'capitalize', background: '#334155', padding: '2px 8px', borderRadius: 4 },
  confidence: { marginLeft: 'auto', color: '#f8fafc', fontSize: '13px' },
  summary:    { color: '#cbd5e1', fontSize: '14px', margin: '0 0 8px' },
  list:       { color: '#94a3b8', fontSize: '12px', paddingLeft: 16, margin: '0 0 8px' },
  footer:     { display: 'flex', gap: 16 },
  meta:       { color: '#64748b', fontSize: '12px' },
};

import { useState } from 'react';
import GovernanceBadge from './GovernanceBadge';

const SENTIMENT_COLOR = {
  bullish: '#16a34a',
  bearish: '#dc2626',
  neutral: '#6b7280',
};

const TIER_LABEL = { 1: 'Blog', 2: 'Major Outlet', 3: 'Wire / SEC' };

export default function SignalCard({ signal }) {
  const [expanded, setExpanded] = useState(false);

  const {
    ticker, eventType, sentiment, confidence, impactSummary,
    timeHorizon, sourceCitations, uncertaintyFactors,
    publishedAt, sourceCredibilityTier, alertSuppressed,
  } = signal;

  return (
    <div style={styles.card}>
      {/* Header row */}
      <div style={styles.header}>
        <span style={styles.ticker}>{ticker}</span>
        <span style={{ ...styles.sentiment, color: SENTIMENT_COLOR[sentiment] ?? '#6b7280' }}>
          {sentiment}
        </span>
        <span style={styles.event}>{eventType}</span>
        <span style={styles.confidence}>{(confidence * 100).toFixed(0)}%</span>
      </div>

      {/* Impact summary */}
      {impactSummary && <p style={styles.summary}>{impactSummary}</p>}

      {/* Expandable detail */}
      {expanded && (
        <div style={styles.detail}>
          {uncertaintyFactors?.length > 0 && (
            <div style={styles.section}>
              <span style={styles.sectionLabel}>Risk factors</span>
              <ul style={styles.list}>
                {uncertaintyFactors.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </div>
          )}

          {sourceCitations?.length > 0 && (
            <div style={styles.section}>
              <span style={styles.sectionLabel}>Sources</span>
              <ul style={styles.list}>
                {sourceCitations.map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div style={styles.footer}>
        <span style={styles.meta}>Horizon: {timeHorizon ?? '—'}</span>
        {sourceCredibilityTier && (
          <span style={styles.meta}>Tier {sourceCredibilityTier}: {TIER_LABEL[sourceCredibilityTier] ?? ''}</span>
        )}
        {alertSuppressed && <span style={styles.suppressed}>Alert suppressed</span>}
        <span style={styles.meta}>{new Date(publishedAt).toLocaleDateString()}</span>
        {(sourceCitations?.length > 0 || uncertaintyFactors?.length > 0) && (
          <button style={styles.toggle} onClick={() => setExpanded(e => !e)}>
            {expanded ? 'Less' : 'More'}
          </button>
        )}
      </div>

      <div style={{ marginTop: 8 }}>
        <GovernanceBadge compact />
      </div>
    </div>
  );
}

const styles = {
  card:         { background: '#1e293b', borderRadius: 8, padding: '16px', marginBottom: 12 },
  header:       { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' },
  ticker:       { fontWeight: '700', fontSize: '16px', color: '#f8fafc' },
  sentiment:    { fontWeight: '600', textTransform: 'capitalize' },
  event:        { color: '#94a3b8', fontSize: '13px', textTransform: 'capitalize', background: '#334155', padding: '2px 8px', borderRadius: 4 },
  confidence:   { marginLeft: 'auto', color: '#f8fafc', fontSize: '13px' },
  summary:      { color: '#cbd5e1', fontSize: '14px', margin: '0 0 8px' },
  detail:       { borderTop: '1px solid #334155', paddingTop: 10, marginTop: 4 },
  section:      { marginBottom: 8 },
  sectionLabel: { display: 'block', color: '#64748b', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 },
  list:         { color: '#94a3b8', fontSize: '12px', paddingLeft: 16, margin: 0 },
  footer:       { display: 'flex', gap: 16, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' },
  meta:         { color: '#64748b', fontSize: '12px' },
  suppressed:   { color: '#92400e', fontSize: '12px', background: '#451a03', padding: '1px 6px', borderRadius: 4 },
  toggle:       { marginLeft: 'auto', background: 'none', border: '1px solid #334155', color: '#94a3b8', fontSize: '12px', padding: '2px 10px', borderRadius: 4, cursor: 'pointer' },
};

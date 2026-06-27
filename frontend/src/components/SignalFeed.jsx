import { useSignals } from '../hooks/useSignals';
import SignalCard from './SignalCard';

export default function SignalFeed({ ticker }) {
  const { signals, loading, error } = useSignals(ticker);

  if (loading) return <p style={styles.state}>Loading signals...</p>;
  if (error)   return <p style={{ ...styles.state, color: '#f87171' }}>Error loading signals.</p>;
  if (!signals.length) return (
    <div style={styles.empty}>
      <p>No signals yet.</p>
      <p style={styles.hint}>Trigger an ingest to fetch news and generate signals.</p>
    </div>
  );

  return (
    <div>
      {signals.map(s => <SignalCard key={s.id} signal={s} />)}
    </div>
  );
}

const styles = {
  state: { color: '#94a3b8', textAlign: 'center', padding: '32px 0' },
  empty: { color: '#94a3b8', textAlign: 'center', padding: '32px 0' },
  hint:  { fontSize: '13px', color: '#64748b' },
};

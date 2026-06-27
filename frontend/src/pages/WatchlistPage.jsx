import WatchlistEditor from '../components/WatchlistEditor';

export default function WatchlistPage() {
  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Watchlist</h1>
      <p style={styles.sub}>Tickers you are monitoring for news and signals.</p>
      <WatchlistEditor />
    </div>
  );
}

const styles = {
  page:  { maxWidth: 640, margin: '0 auto', padding: '32px 16px' },
  title: { color: '#f8fafc', fontSize: 24, fontWeight: 700, margin: '0 0 4px' },
  sub:   { color: '#94a3b8', fontSize: 14, margin: '0 0 24px' },
};

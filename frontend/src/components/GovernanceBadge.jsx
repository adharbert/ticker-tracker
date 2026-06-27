export default function GovernanceBadge() {
  return (
    <div style={styles.badge}>
      NOT FINANCIAL ADVICE &mdash; Educational analysis only
    </div>
  );
}

const styles = {
  badge: {
    background:   '#7f1d1d',
    color:        '#fca5a5',
    padding:      '6px 12px',
    borderRadius: '4px',
    fontSize:     '11px',
    fontWeight:   '600',
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    display:      'inline-block',
  },
};

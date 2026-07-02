import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

export default function SentimentChart({ data, ticker, name }) {
  if (!data?.length) return null;

  const prices   = data.map(d => d.price).filter(Boolean);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const range    = maxPrice - minPrice || 1;

  const chartData = data.map(d => ({
    date:            d.date,
    sentiment:       d.confidence ?? null,
    normalizedPrice: d.price != null ? (d.price - minPrice) / range : null,
    rawPrice:        d.price,
    sentimentLabel:  d.sentiment,
  }));

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <div style={{ marginBottom: '0.5rem' }}>
        <span style={{ fontWeight: 700, fontSize: '1rem', color: '#f8fafc' }}>{ticker}</span>
        {name && <span style={{ color: '#94a3b8', fontSize: '0.9rem', marginLeft: 8 }}>{name}</span>}
        <span style={{ color: '#64748b', fontSize: '0.8rem', marginLeft: 8 }}>· Price &amp; Sentiment</span>
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="score" domain={[0, 1]} tick={{ fontSize: 11 }}
            label={{ value: 'Confidence', angle: -90, position: 'insideLeft', fontSize: 10 }} />
          <YAxis yAxisId="price" orientation="right" tick={{ fontSize: 11 }}
            label={{ value: 'Price (norm.)', angle: 90, position: 'insideRight', fontSize: 10 }} />
          <Tooltip
            formatter={(value, name, props) => {
              if (name === 'Price') return [`$${props.payload.rawPrice?.toFixed(2)}`, 'Price'];
              return [`${(value * 100).toFixed(0)}%`, 'Sentiment Confidence'];
            }}
          />
          <Legend />
          <Line yAxisId="score" type="monotone" dataKey="sentiment"
            stroke="#3b82f6" dot={{ r: 3 }} name="Sentiment" connectNulls />
          <Line yAxisId="price" type="monotone" dataKey="normalizedPrice"
            stroke="#10b981" dot={false} name="Price" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

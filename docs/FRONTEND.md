# Frontend — React Specification

> Claude Code: implement all files in `frontend/` using this spec.
> Read `docs/API.md` for the exact API response shapes this UI depends on.

---

## Project setup

```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install recharts        # sentiment + price charts
npm install swr             # data fetching with polling
npm install react-router-dom # navigation
npm run dev                 # → http://localhost:5173
```

### `frontend/.env`

```bash
VITE_API_URL=http://localhost:5000
```

---

## Component map

```
App.jsx  (React Router)
│
├── /                → DashboardPage
│   ├── SignalFeed           — paginated list of signals
│   │   └── SignalCard       — single signal with confidence + disclaimer
│   └── SentimentChart       — Recharts: sentiment vs price over time
│
├── /watchlist       → WatchlistPage
│   └── WatchlistEditor      — add/remove tickers
│
├── /digest          → DigestPage
│   └── DigestCard           — daily digest summary per ticker
│
└── /backtest/:ticker → BacktestPage          (Phase 3)
    └── BacktestResultCard   — accuracy vs baseline with disclaimers
```

---

## File: `frontend/src/App.jsx`

```jsx
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import DashboardPage  from "./pages/DashboardPage";
import WatchlistPage  from "./pages/WatchlistPage";
import DigestPage     from "./pages/DigestPage";
import BacktestPage   from "./pages/BacktestPage";

const navStyle  = { textDecoration: "none", color: "#374151", padding: "0.5rem 1rem" };
const activeStyle = { ...navStyle, fontWeight: 600, borderBottom: "2px solid #2563eb" };

export default function App() {
  return (
    <BrowserRouter>
      <nav style={{ borderBottom: "1px solid #e5e7eb", display: "flex", padding: "0 1rem" }}>
        <NavLink to="/"          style={({ isActive }) => isActive ? activeStyle : navStyle}>Dashboard</NavLink>
        <NavLink to="/watchlist" style={({ isActive }) => isActive ? activeStyle : navStyle}>Watchlist</NavLink>
        <NavLink to="/digest"    style={({ isActive }) => isActive ? activeStyle : navStyle}>Digest</NavLink>
      </nav>
      <main style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto" }}>
        <Routes>
          <Route path="/"                  element={<DashboardPage />} />
          <Route path="/watchlist"         element={<WatchlistPage />} />
          <Route path="/digest"            element={<DigestPage />} />
          <Route path="/backtest/:ticker"  element={<BacktestPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}
```

---

## File: `frontend/src/api/marketApi.js`

All API calls go through this module. Never call `fetch` directly from components.

```javascript
const BASE = import.meta.env.VITE_API_URL;

export async function getSignals({ ticker, limit = 20, from } = {}) {
  const params = new URLSearchParams();
  if (ticker) params.set("ticker", ticker);
  if (limit)  params.set("limit",  limit);
  if (from)   params.set("from",   from);
  const res = await fetch(`${BASE}/api/signals?${params}`);
  if (!res.ok) throw new Error(`signals fetch failed: ${res.status}`);
  return res.json();
}

export async function getSignalById(id) {
  const res = await fetch(`${BASE}/api/signals/${id}`);
  if (!res.ok) throw new Error(`signal ${id} not found`);
  return res.json();
}

export async function getDigest() {
  const res = await fetch(`${BASE}/api/digest/latest`);
  if (!res.ok) throw new Error("digest fetch failed");
  return res.json();
}

export async function getWatchlist() {
  const res = await fetch(`${BASE}/api/watchlist`);
  if (!res.ok) throw new Error("watchlist fetch failed");
  return res.json();
}

export async function addWatchlistItem(ticker, name = "") {
  const res = await fetch(`${BASE}/api/watchlist`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ ticker: ticker.toUpperCase(), name }),
  });
  if (!res.ok) throw new Error("add watchlist item failed");
  return res.json();
}

export async function removeWatchlistItem(ticker) {
  const res = await fetch(`${BASE}/api/watchlist/${ticker}`, { method: "DELETE" });
  if (!res.ok) throw new Error("remove watchlist item failed");
}

export async function getBacktest(ticker) {
  const res = await fetch(`${BASE}/api/backtest/${ticker}`);
  if (!res.ok) throw new Error(`backtest fetch failed: ${res.status}`);
  return res.json();
}

export async function triggerIngest() {
  const res = await fetch(`${BASE}/api/ingest/trigger`, { method: "POST" });
  if (!res.ok) throw new Error("ingest trigger failed");
  return res.json();
}
```

---

## File: `frontend/src/hooks/useSignals.js`

SWR-based polling. Signals refresh automatically every 30 seconds.

```javascript
import useSWR from "swr";
import { getSignals } from "../api/marketApi";

const fetcher = (opts) => getSignals(opts);

export function useSignals({ ticker, limit = 20 } = {}) {
  const { data, error, isLoading, mutate } = useSWR(
    ["signals", ticker, limit],
    () => fetcher({ ticker, limit }),
    { refreshInterval: 30_000 }     // poll every 30s
  );

  return {
    signals:   data ?? [],
    isLoading,
    error,
    refresh:   mutate,
  };
}
```

---

## File: `frontend/src/hooks/useWatchlist.js`

```javascript
import { useState, useEffect } from "react";
import { getWatchlist, addWatchlistItem, removeWatchlistItem } from "../api/marketApi";

export function useWatchlist() {
  const [items,     setItems]     = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error,     setError]     = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      setIsLoading(true);
      setItems(await getWatchlist());
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  }

  async function add(ticker, name = "") {
    await addWatchlistItem(ticker, name);
    await load();
  }

  async function remove(ticker) {
    await removeWatchlistItem(ticker);
    setItems(items.filter(i => i.ticker !== ticker));
  }

  return { items, isLoading, error, add, remove, refresh: load };
}
```

---

## File: `frontend/src/components/GovernanceBadge.jsx`

Rendered on EVERY SignalCard and BacktestPage.
Never make this dismissible or hide it conditionally.

```jsx
export default function GovernanceBadge({ compact = false }) {
  if (compact) {
    return (
      <span style={{
        display:       "inline-block",
        padding:       "2px 8px",
        background:    "#fee2e2",
        color:         "#991b1b",
        borderRadius:  4,
        fontSize:      "0.7rem",
        fontWeight:    600,
        letterSpacing: "0.02em",
      }}>
        NOT FINANCIAL ADVICE
      </span>
    );
  }

  return (
    <div style={{
      padding:      "0.5rem 0.75rem",
      background:   "#fee2e2",
      border:       "1px solid #fecaca",
      borderRadius: 6,
      fontSize:     "0.8rem",
      color:        "#7f1d1d",
      lineHeight:   1.5,
      margin:       "0.5rem 0",
    }}>
      <strong>Educational analysis only.</strong> This output is generated by AI
      and may be incorrect. Past correlations do not predict future price movements.
      Do not make investment decisions based on this content.
    </div>
  );
}
```

---

## File: `frontend/src/components/SignalCard.jsx`

```jsx
import GovernanceBadge from "./GovernanceBadge";

const SENTIMENT_COLORS = {
  bullish: { bg: "#dcfce7", border: "#86efac", text: "#166534" },
  bearish: { bg: "#fee2e2", border: "#fca5a5", text: "#991b1b" },
  neutral: { bg: "#f3f4f6", border: "#d1d5db", text: "#374151" },
};

export default function SignalCard({ signal }) {
  const colors = SENTIMENT_COLORS[signal.sentiment] ?? SENTIMENT_COLORS.neutral;
  const pct    = Math.round(signal.confidence * 100);

  return (
    <article style={{
      border:       `1px solid ${colors.border}`,
      borderRadius: 8,
      padding:      "1rem",
      background:   "#fff",
      marginBottom: "0.75rem",
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <span style={{ fontWeight: 700, fontSize: "1.1rem" }}>{signal.ticker}</span>
          <span style={{
            marginLeft:   "0.5rem",
            padding:      "2px 8px",
            background:   colors.bg,
            color:        colors.text,
            borderRadius: 4,
            fontSize:     "0.8rem",
            fontWeight:   600,
          }}>
            {signal.sentiment.toUpperCase()}
          </span>
          <span style={{ marginLeft: "0.5rem", color: "#6b7280", fontSize: "0.85rem" }}>
            {signal.eventType}
          </span>
        </div>
        <GovernanceBadge compact />
      </div>

      {/* Confidence bar */}
      <div style={{ margin: "0.75rem 0 0.5rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "#6b7280" }}>
          <span>Confidence</span>
          <span>{pct}%</span>
        </div>
        <div style={{ background: "#e5e7eb", borderRadius: 4, height: 6, marginTop: 4 }}>
          <div style={{
            width:        `${pct}%`,
            height:       "100%",
            background:   pct >= 80 ? "#f59e0b" : pct >= 65 ? "#3b82f6" : "#9ca3af",
            borderRadius: 4,
            transition:   "width 0.3s ease",
          }} />
        </div>
      </div>

      {/* Impact summary */}
      <p style={{ margin: "0.5rem 0", fontSize: "0.9rem", lineHeight: 1.6 }}>
        {signal.impactSummary}
      </p>

      {/* Uncertainty factors */}
      {signal.uncertaintyFactors?.length > 0 && (
        <details style={{ marginTop: "0.5rem", fontSize: "0.85rem", color: "#6b7280" }}>
          <summary>Uncertainty factors</summary>
          <ul style={{ margin: "0.25rem 0 0 1rem", padding: 0 }}>
            {signal.uncertaintyFactors.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </details>
      )}

      {/* Source citations */}
      {signal.sourceCitations?.length > 0 && (
        <div style={{ marginTop: "0.5rem", fontSize: "0.8rem", color: "#9ca3af" }}>
          Source: {signal.sourceCitations.join(", ")}
        </div>
      )}

      {/* Governance warnings */}
      {signal.governanceWarnings?.length > 0 && (
        <div style={{
          marginTop: "0.5rem", padding: "0.4rem 0.6rem",
          background: "#fef9c3", borderRadius: 4, fontSize: "0.8rem", color: "#713f12",
        }}>
          {signal.governanceWarnings.map((w, i) => <div key={i}>{w}</div>)}
        </div>
      )}

      {/* Published time */}
      <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "#9ca3af" }}>
        {new Date(signal.publishedAt).toLocaleString()}
        {" · Tier "}{signal.sourceCredibilityTier}
      </div>
    </article>
  );
}
```

---

## File: `frontend/src/components/SignalFeed.jsx`

```jsx
import { useState } from "react";
import { useSignals } from "../hooks/useSignals";
import SignalCard from "./SignalCard";

const EVENT_TYPES = ["all", "fed_rate", "earnings", "merger", "regulatory", "macro"];

export default function SignalFeed() {
  const [ticker,    setTicker]    = useState("");
  const [eventType, setEventType] = useState("all");
  const { signals, isLoading, error, refresh } = useSignals({ ticker: ticker || undefined });

  const filtered = eventType === "all"
    ? signals
    : signals.filter(s => s.eventType === eventType);

  return (
    <section>
      {/* Filters */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <input
          placeholder="Filter by ticker (e.g. AAPL)"
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          style={{ padding: "0.4rem 0.75rem", borderRadius: 6, border: "1px solid #d1d5db" }}
        />
        <select
          value={eventType}
          onChange={e => setEventType(e.target.value)}
          style={{ padding: "0.4rem 0.75rem", borderRadius: 6, border: "1px solid #d1d5db" }}
        >
          {EVENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <button onClick={refresh}
          style={{ padding: "0.4rem 0.75rem", borderRadius: 6, background: "#2563eb", color: "#fff", border: "none", cursor: "pointer" }}>
          Refresh
        </button>
      </div>

      {isLoading && <p>Loading signals...</p>}
      {error     && <p style={{ color: "#dc2626" }}>Error: {error}</p>}
      {!isLoading && filtered.length === 0 && (
        <p style={{ color: "#6b7280" }}>
          No signals yet. Run `curl -X POST http://localhost:5000/api/ingest/trigger` to start.
        </p>
      )}
      {filtered.map(s => <SignalCard key={s.id} signal={s} />)}
    </section>
  );
}
```

---

## File: `frontend/src/components/SentimentChart.jsx`

Recharts line chart: FinBERT confidence score vs. closing price over time.
Two Y-axes: left for normalized price, right for sentiment confidence (0-1).

```jsx
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";

export default function SentimentChart({ data, ticker }) {
  // data: [{ date, price, confidence, sentiment }]
  // Normalize price to 0-1 range for dual-axis display
  const prices   = data.map(d => d.price).filter(Boolean);
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const range    = maxPrice - minPrice || 1;

  const chartData = data.map(d => ({
    date:              d.date,
    sentiment:         d.confidence ?? null,
    normalizedPrice:   d.price != null ? (d.price - minPrice) / range : null,
    rawPrice:          d.price,
    sentimentLabel:    d.sentiment,
  }));

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h3 style={{ marginBottom: "0.5rem" }}>
        {ticker} — Sentiment vs Price
      </h3>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="score"  domain={[0, 1]}  tick={{ fontSize: 11 }} label={{ value: "Confidence", angle: -90, position: "insideLeft", fontSize: 11 }} />
          <YAxis yAxisId="price"  orientation="right" tick={{ fontSize: 11 }} label={{ value: "Price (normalized)", angle: 90, position: "insideRight", fontSize: 11 }} />
          <Tooltip
            formatter={(value, name, props) => {
              if (name === "Price") return [`$${props.payload.rawPrice?.toFixed(2)}`, "Price"];
              return [`${(value * 100).toFixed(0)}%`, "Sentiment Confidence"];
            }}
          />
          <Legend />
          <Line yAxisId="score" type="monotone" dataKey="sentiment"       stroke="#3b82f6" dot={false} name="Sentiment" />
          <Line yAxisId="price" type="monotone" dataKey="normalizedPrice" stroke="#10b981" dot={false} name="Price" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
```

---

## File: `frontend/src/components/WatchlistEditor.jsx`

```jsx
import { useState } from "react";
import { useWatchlist } from "../hooks/useWatchlist";

export default function WatchlistEditor() {
  const { items, isLoading, add, remove } = useWatchlist();
  const [input, setInput] = useState("");
  const [adding, setAdding] = useState(false);

  async function handleAdd() {
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    try {
      await add(ticker);
      setInput("");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <input
          placeholder="Ticker (e.g. NVDA)"
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === "Enter" && handleAdd()}
          style={{ padding: "0.4rem 0.75rem", borderRadius: 6, border: "1px solid #d1d5db", width: 160 }}
        />
        <button onClick={handleAdd} disabled={adding}
          style={{ padding: "0.4rem 0.75rem", borderRadius: 6, background: "#2563eb", color: "#fff", border: "none", cursor: "pointer" }}>
          {adding ? "Adding..." : "Add"}
        </button>
      </div>

      {isLoading && <p>Loading...</p>}

      <ul style={{ listStyle: "none", padding: 0 }}>
        {items.map(item => (
          <li key={item.ticker} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "0.5rem 0.75rem", borderRadius: 6, background: "#f9fafb",
            marginBottom: "0.4rem",
          }}>
            <div>
              <strong>{item.ticker}</strong>
              {item.name && <span style={{ color: "#6b7280", marginLeft: "0.5rem", fontSize: "0.9rem" }}>{item.name}</span>}
            </div>
            <button onClick={() => remove(item.ticker)}
              style={{ padding: "2px 8px", borderRadius: 4, background: "#fee2e2", color: "#991b1b", border: "none", cursor: "pointer", fontSize: "0.85rem" }}>
              Remove
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## File: `frontend/src/pages/DashboardPage.jsx`

```jsx
import SignalFeed      from "../components/SignalFeed";
import SentimentChart  from "../components/SentimentChart";

export default function DashboardPage() {
  return (
    <div>
      <h1 style={{ marginBottom: "1.5rem" }}>Market Signal Dashboard</h1>
      {/* SentimentChart: wire up once prices + signals exist in DB */}
      <SignalFeed />
    </div>
  );
}
```

---

## File: `frontend/src/pages/WatchlistPage.jsx`

```jsx
import WatchlistEditor from "../components/WatchlistEditor";

export default function WatchlistPage() {
  return (
    <div>
      <h1 style={{ marginBottom: "1.5rem" }}>Watchlist</h1>
      <p style={{ color: "#6b7280", marginBottom: "1rem" }}>
        Tickers added here will be included in the next news ingestion run.
      </p>
      <WatchlistEditor />
    </div>
  );
}
```

---

## File: `frontend/src/pages/BacktestPage.jsx` (Phase 3)

```jsx
import { useParams } from "react-router-dom";
import { useState, useEffect } from "react";
import GovernanceBadge from "../components/GovernanceBadge";
import { getBacktest } from "../api/marketApi";

export default function BacktestPage() {
  const { ticker }  = useParams();
  const [data,  setData]  = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getBacktest(ticker).then(setData).catch(e => setError(e.message));
  }, [ticker]);

  return (
    <div>
      {/* Title must use "Evaluation", not "Predictions" */}
      <h1>Signal Evaluation (Backtesting) — {ticker}</h1>

      <div style={{
        background: "#eff6ff", border: "1px solid #bfdbfe",
        borderRadius: 6, padding: "0.75rem", marginBottom: "1.5rem", fontSize: "0.9rem",
      }}>
        This page measures how well past signals correlated with actual price moves.
        It does not predict future movements.
      </div>

      <GovernanceBadge />

      {error && <p style={{ color: "#dc2626" }}>Error: {error}</p>}
      {!data && !error && <p>Loading backtest data...</p>}

      {data && (
        <div style={{ marginTop: "1rem" }}>
          <div style={{ display: "flex", gap: "2rem", flexWrap: "wrap" }}>
            <Stat label="Your signals"    value={data.accuracy != null ? `${(data.accuracy * 100).toFixed(1)}%` : "—"} />
            <Stat label="Coin flip"       value="50.0%" />
            <Stat label="Edge"            value={data.vsBaseline != null ? `+${(data.vsBaseline * 100).toFixed(1)}%` : "—"} />
            <Stat label="Sample size"     value={data.sampleSize} />
            <Stat label="Look-ahead"      value={`${data.lookAheadDays} days`} />
          </div>

          {data.accuracyNote && (
            <div style={{ marginTop: "1rem", color: "#92400e", background: "#fef3c7", padding: "0.5rem 0.75rem", borderRadius: 6 }}>
              {data.accuracyNote}
            </div>
          )}

          {data.governanceWarnings?.map((w, i) => (
            <div key={i} style={{ marginTop: "0.5rem", color: "#92400e", background: "#fef3c7", padding: "0.5rem 0.75rem", borderRadius: 6 }}>
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: "0.8rem", color: "#6b7280" }}>{label}</div>
    </div>
  );
}
```

---

## Claude Code instructions for this layer

1. The `GovernanceBadge` component must appear on every `SignalCard` and `BacktestPage` —
   never remove it, hide it, or make it dismissible
2. `BacktestPage` title must read "Signal Evaluation (Backtesting)" — never "Predictions"
3. SWR's `refreshInterval` of 30s is intentional — don't reduce it, avoid hammering the API
4. All API calls go through `marketApi.js` — never call `fetch` from components directly
5. Source credibility tier should be visible on SignalCard so users can evaluate source quality
6. For the SentimentChart, fetch price data separately from signals — they have different
   update cadences (prices daily, signals whenever news arrives)

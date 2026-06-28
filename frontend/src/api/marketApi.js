const BASE = import.meta.env.VITE_API_URL;

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) throw new Error(`${options.method ?? 'GET'} ${path} → ${res.status}`);
  if (res.status === 204) return null;
  return res.json();
}

export const getWatchlist   = ()               => request('/api/watchlist');
export const addTicker      = (ticker, name)   => request('/api/watchlist', {
  method:  'POST',
  headers: { 'Content-Type': 'application/json' },
  body:    JSON.stringify({ ticker, name }),
});
export const removeTicker   = (ticker)         => request(`/api/watchlist/${ticker}`, { method: 'DELETE' });
export const getSignals     = (ticker, limit)  => request(`/api/signals?${new URLSearchParams({ ...(ticker ? { ticker } : {}), limit: limit ?? 20 })}`);
export const triggerIngest  = ()               => request('/api/ingest/trigger', { method: 'POST' });
export const getPrices      = (ticker, days)   => request(`/api/prices/${ticker}?days=${days ?? 30}`);

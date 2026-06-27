import useSWR from 'swr';
import { getWatchlist, addTicker, removeTicker } from '../api/marketApi';

export function useWatchlist() {
  const { data, error, mutate } = useSWR('/api/watchlist', getWatchlist, {
    refreshInterval: 30_000,
  });

  async function add(ticker, name) {
    await addTicker(ticker.toUpperCase(), name);
    mutate();
  }

  async function remove(ticker) {
    await removeTicker(ticker);
    mutate();
  }

  return {
    watchlist: data ?? [],
    loading:   !data && !error,
    error,
    add,
    remove,
  };
}

import useSWR from 'swr';
import { getSignals } from '../api/marketApi';

export function useSignals(ticker) {
  const key = ticker ? `/api/signals?ticker=${ticker}` : '/api/signals';
  const { data, error, mutate } = useSWR(
    key,
    () => getSignals(ticker),
    { refreshInterval: 60_000 }
  );

  return {
    signals: data ?? [],
    loading: !data && !error,
    error,
    mutate,
  };
}

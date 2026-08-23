import { useEffect, useState } from 'react';
import { health } from '../lib/api';

export type Online = boolean | null;

/** Polls GET /health; null while the first check is in flight. */
export function useHealth(intervalMs = 10000): Online {
  const [online, setOnline] = useState<Online>(null);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const ok = await health();
      if (!cancelled) setOnline(ok);
    };
    check();
    const id = window.setInterval(check, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [intervalMs]);

  return online;
}

import { useCallback, useEffect, useState } from 'react';
import { fetchAddons, toggleAddon } from '../lib/api';
import type { AddonInfo } from '../types';

interface AddonsState {
  addons: AddonInfo[];
  loading: boolean;
  error: string | null;
  /** Name of an add-on whose toggle is mid-request (optimistic update). */
  pending: string | null;
}

/**
 * Add-on toggle state for one session. Toggles apply optimistically and roll
 * back with the server's error message when the POST fails.
 */
export function useAddons(sessionId: string | null) {
  const [state, setState] = useState<AddonsState>({
    addons: [],
    loading: true,
    error: null,
    pending: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetchAddons(sessionId)
      .then((addons) => {
        if (!cancelled) setState((s) => ({ ...s, addons, loading: false }));
      })
      .catch((err) => {
        if (!cancelled) {
          setState((s) => ({
            ...s,
            loading: false,
            error: err instanceof Error ? err.message : 'Failed to load add-ons.',
          }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const toggle = useCallback(
    async (addon: AddonInfo) => {
      if (!sessionId || state.pending) return;
      const next = !addon.enabled;
      // Optimistic flip; rolled back below on any failure.
      setState((s) => ({
        ...s,
        pending: addon.name,
        addons: s.addons.map((f) => (f.name === addon.name ? { ...f, enabled: next } : f)),
      }));
      try {
        await toggleAddon(addon.name, next, sessionId);
        setState((s) => ({ ...s, pending: null }));
      } catch (err) {
        setState((s) => ({
          ...s,
          pending: null,
          error: err instanceof Error ? err.message : 'Toggle failed.',
          addons: s.addons.map((f) =>
            f.name === addon.name ? { ...f, enabled: addon.enabled } : f,
          ),
        }));
      }
    },
    [sessionId, state.pending],
  );

  return { ...state, toggle };
}

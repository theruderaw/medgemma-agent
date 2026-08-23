import { useCallback, useEffect, useState } from 'react';
import { fetchFeatures, toggleFeature } from '../lib/api';
import type { FeatureInfo } from '../types';

interface FeaturesState {
  features: FeatureInfo[];
  loading: boolean;
  error: string | null;
  /** Name of a feature whose toggle is mid-request (optimistic update). */
  pending: string | null;
}

/**
 * Add-on toggle state for one session. Toggles apply optimistically and roll
 * back with the server's error message when the POST fails.
 */
export function useFeatures(sessionId: string | null) {
  const [state, setState] = useState<FeaturesState>({
    features: [],
    loading: true,
    error: null,
    pending: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetchFeatures(sessionId)
      .then((features) => {
        if (!cancelled) setState((s) => ({ ...s, features, loading: false }));
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
    async (feature: FeatureInfo) => {
      if (!sessionId || state.pending) return;
      const next = !feature.enabled;
      // Optimistic flip; rolled back below on any failure.
      setState((s) => ({
        ...s,
        pending: feature.name,
        features: s.features.map((f) => (f.name === feature.name ? { ...f, enabled: next } : f)),
      }));
      try {
        await toggleFeature(feature.name, next, sessionId);
        setState((s) => ({ ...s, pending: null }));
      } catch (err) {
        setState((s) => ({
          ...s,
          pending: null,
          error: err instanceof Error ? err.message : 'Toggle failed.',
          features: s.features.map((f) =>
            f.name === feature.name ? { ...f, enabled: feature.enabled } : f,
          ),
        }));
      }
    },
    [sessionId, state.pending],
  );

  return { ...state, toggle };
}

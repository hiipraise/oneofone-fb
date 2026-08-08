import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const QueryContext = createContext(null);

export class QueryClient {
  constructor(options = {}) {
    this.defaultOptions = options.defaultOptions || {};
    this.cache = new Map();
  }
}

export function QueryClientProvider({ client, children }) {
  const stableClient = useMemo(() => client, [client]);
  return <QueryContext.Provider value={stableClient}>{children}</QueryContext.Provider>;
}

const keyOf = (key) => JSON.stringify(key);

export function useQuery(options) {
  const client = useContext(QueryContext) || new QueryClient();
  const defaults = client.defaultOptions?.queries || {};
  const staleTime = options.staleTime ?? defaults.staleTime ?? 0;
  const cacheKey = keyOf(options.queryKey);
  const [state, setState] = useState(() => {
    const cached = client.cache.get(cacheKey);
    const fresh = cached && Date.now() - cached.updatedAt < staleTime;
    return { data: fresh ? cached.data : undefined, error: null, isLoading: !fresh };
  });

  const run = useCallback(async () => {
    const cached = client.cache.get(cacheKey);
    if (cached?.promise) return cached.promise;
    if (cached && Date.now() - cached.updatedAt < staleTime) {
      setState({ data: cached.data, error: null, isLoading: false });
      return { data: cached.data };
    }
    setState((prev) => ({ ...prev, isLoading: prev.data === undefined }));
    const promise = options.queryFn()
      .then((data) => {
        client.cache.set(cacheKey, { data, updatedAt: Date.now(), promise: null });
        setState({ data, error: null, isLoading: false });
        return { data };
      })
      .catch((error) => {
        client.cache.set(cacheKey, { ...(client.cache.get(cacheKey) || {}), promise: null });
        setState((prev) => ({ ...prev, error, isLoading: false }));
        throw error;
      });
    client.cache.set(cacheKey, { ...(cached || {}), promise });
    return promise;
  }, [cacheKey, client, options.queryFn, staleTime]);

  useEffect(() => {
    run().catch(() => undefined);
  }, [run]);

  useEffect(() => {
    if (!options.refetchInterval || options.refetchInterval < 1000) return undefined;
    const id = setInterval(() => {
      if (!options.refetchIntervalInBackground && typeof document !== "undefined" && document.hidden) return;
      run().catch(() => undefined);
    }, options.refetchInterval);
    return () => clearInterval(id);
  }, [options.refetchInterval, options.refetchIntervalInBackground, run]);

  return { ...state, refetch: run };
}

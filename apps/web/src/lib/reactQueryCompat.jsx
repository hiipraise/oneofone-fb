// React Query v5 — thin re-export shim.
//
// The app previously shipped a hand-rolled cache (in-memory Map + manual
// in-flight dedup). Per Sprint 1 of the remediation plan, the real
// @tanstack/react-query library is used instead; this file keeps the existing
// import path (`../lib/reactQueryCompat.jsx`) stable so no call site changes.
//
// `useQuery({ queryKey, queryFn, staleTime, refetchInterval, ... })` returns
// `{ data, error, isLoading, isFetching, refetch, ... }` — the same surface the
// hooks in `useData.js` already consume.
export { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

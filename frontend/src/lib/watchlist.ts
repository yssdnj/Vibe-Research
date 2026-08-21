import { api } from "@/lib/api";

export const loadWatch = () => api.watchlist();
export const saveWatch = (codes: string[]) => api.saveWatchlist(codes);

export function parseCodes(raw: string): string[] {
  const tokens = raw.split(/[^\d]+/).filter(Boolean);
  return Array.from(new Set(tokens.filter((token) => /^\d{6}$/.test(token))));
}

export function addCodes(existing: string[], raw: string): { next: string[]; added: number } {
  const incoming = parseCodes(raw).filter((code) => !existing.includes(code));
  return { next: [...existing, ...incoming], added: incoming.length };
}

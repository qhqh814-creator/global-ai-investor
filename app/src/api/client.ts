export interface Provenance {
  sourceIds: string[];
  quoteTime?: string;
  fetchedAt?: string;
  isRealtime: boolean;
  kind: 'realtime_licensed' | 'delayed' | 'eod_close' | 'snapshot_unknown';
  licenseStatus: 'licensed' | 'public_page' | 'unlicensed_third_party' | 'unknown';
  dataUnavailableReason?: string;
}

export interface DataResult<T> {
  value: T | null;
  provenance: Provenance | null;
  unavailableReason?: string;
}

let backendPromise: Promise<{ baseUrl: string; token: string } | null> | null = null;

export async function getBackend(): Promise<{ baseUrl: string; token: string } | null> {
  if (!backendPromise) {
    backendPromise = (async () => {
      try {
        const info = await window.gai.getBackend();
        if (info.status !== 'running') return null;
        return { baseUrl: info.baseUrl, token: info.token };
      } catch {
        return null;
      }
    })();
  }
  return backendPromise;
}

export async function apiGet<T>(path: string): Promise<DataResult<T>> {
  const backend = await getBackend();
  if (!backend) {
    return { value: null, provenance: null, unavailableReason: 'backend_unavailable' };
  }
  try {
    const res = await fetch(`${backend.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${backend.token}` }
    });
    if (!res.ok) {
      return { value: null, provenance: null, unavailableReason: `http_${res.status}` };
    }
    return (await res.json()) as DataResult<T>;
  } catch {
    return { value: null, provenance: null, unavailableReason: 'network_error' };
  }
}

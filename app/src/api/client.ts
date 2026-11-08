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

export interface DashboardCard {
  key: string;
  value: string | null;
  status: 'available' | 'unavailable';
  reason: string | null;
  provenance: Provenance | null;
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

async function request(path: string): Promise<Response | null> {
  const backend = await getBackend();
  if (!backend) return null;
  try {
    return await fetch(`${backend.baseUrl}${path}`, {
      headers: { Authorization: `Bearer ${backend.token}` }
    });
  } catch {
    return null;
  }
}

export async function apiGet<T>(path: string): Promise<DataResult<T>> {
  const res = await request(path);
  if (!res) return { value: null, provenance: null, unavailableReason: 'backend_unavailable' };
  if (!res.ok) return { value: null, provenance: null, unavailableReason: `http_${res.status}` };
  return (await res.json()) as DataResult<T>;
}

export async function apiGetRaw<T>(path: string): Promise<T | null> {
  const res = await request(path);
  if (!res || !res.ok) return null;
  return (await res.json()) as T;
}

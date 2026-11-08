import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiDelete, apiGetRaw, apiPost } from '../../api/client';

interface WatchItem {
  code: string;
  name_zh: string | null;
  exchange: string | null;
  board: string | null;
  last: number | null;
  change_pct: number | null;
  quote_time: string | null;
  note: string | null;
}

export default function Watchlist() {
  const { t } = useTranslation();
  const [items, setItems] = useState<WatchItem[]>([]);
  const [code, setCode] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const data = await apiGetRaw<{ items: WatchItem[] }>('/api/watchlist');
    setItems(data?.items ?? []);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const add = async () => {
    const trimmed = code.trim();
    if (!trimmed) return;
    const res = await apiPost<{ ok: boolean; added: boolean }>('/api/watchlist/items', { code: trimmed });
    setMessage(res?.ok ? (res.added ? t('watchlist.added') : t('watchlist.exists')) : t('watchlist.failed'));
    setCode('');
    await load();
  };

  const remove = async (target: string) => {
    await apiDelete(`/api/watchlist/items/${target}`);
    await load();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('watchlist.title')}</h1>
          <p className="subtitle">{t('watchlist.subtitle')}</p>
        </div>
        <div className="row">
          <input
            className="input"
            value={code}
            placeholder={t('watchlist.placeholder')}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void add()}
          />
          <button className="chip" onClick={() => void add()}>
            {t('watchlist.add')}
          </button>
        </div>
      </header>

      {message && <p className="meta">{message}</p>}
      {loading && <p className="meta">{t('data.loading')}</p>}
      {!loading && items.length === 0 && <p className="meta">{t('watchlist.empty')}</p>}

      <div className="list">
        {items.map((item) => (
          <div className="list-row" key={item.code}>
            <div className="list-main">
              <div className="list-title">
                {item.name_zh ?? '—'} <span className="meta">{item.code}</span>
              </div>
              <div className="meta">
                {item.exchange}/{item.board} · {item.last ?? '—'} ({item.change_pct ?? '—'}%) ·{' '}
                {item.quote_time ?? '—'}
              </div>
            </div>
            <button className="chip" onClick={() => void remove(item.code)}>
              {t('watchlist.remove')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}


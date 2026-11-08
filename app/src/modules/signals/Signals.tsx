import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface SignalItem {
  id: number;
  code: string;
  name_zh: string | null;
  side: string;
  trade_date: string;
  price: number | null;
  change_pct: number | null;
  triggered_at: string;
  rule_name: string | null;
}

export default function Signals() {
  const { t } = useTranslation();
  const [items, setItems] = useState<SignalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async () => {
    const data = await apiGetRaw<{ items: SignalItem[] }>('/api/signals?limit=50');
    setItems(data?.items ?? []);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const run = async () => {
    setRunning(true);
    await apiPost('/api/signals/run');
    await load();
    setRunning(false);
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('signals.title')}</h1>
          <p className="subtitle">{t('signals.subtitle')}</p>
        </div>
        <button className="chip" onClick={() => void run()} disabled={running}>
          {running ? '…' : t('signals.run')}
        </button>
      </header>

      {loading && <p className="meta">{t('data.loading')}</p>}
      {!loading && items.length === 0 && <p className="meta">{t('signals.empty')}</p>}

      <div className="list">
        {items.map((item) => (
          <div className="list-row" key={item.id}>
            <div className={item.side === 'BUY' ? 'level-badge buy' : 'level-badge sell'}>{item.side}</div>
            <div className="list-main">
              <div className="list-title">
                {item.name_zh ?? '—'} <span className="meta">{item.code}</span> · {item.rule_name}
              </div>
              <div className="meta">
                {item.price ?? '—'} ({item.change_pct ?? '—'}%) · {item.trade_date} · {item.triggered_at}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


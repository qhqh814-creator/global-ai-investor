import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface AlertItem {
  id: number;
  level: string;
  title: string;
  summary: string | null;
  status: string;
  triggered_at: string;
  evidence: Array<{ quote: string; source_url: string }>;
}

export default function Alerts() {
  const { t } = useTranslation();
  const [items, setItems] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const data = await apiGetRaw<{ items: AlertItem[] }>('/api/alerts?limit=50');
    setItems(data?.items ?? []);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const ackAll = async () => {
    const open = items.filter((i) => i.status === 'OPEN');
    await Promise.all(open.map((i) => apiPost(`/api/alerts/${i.id}/ack`)));
    await load();
  };

  const ack = async (id: number) => {
    await apiPost(`/api/alerts/${id}/ack`);
    await load();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('alerts.title')}</h1>
          <p className="subtitle">{t('alerts.subtitle')}</p>
        </div>
        <div className="row">
          <button className="chip" onClick={() => void load()}>{t('alerts.refresh')}</button>
          <button className="chip primary" onClick={() => void ackAll()} disabled={items.filter((i) => i.status === 'OPEN').length === 0}>{t('alerts.ackAll')}</button>
        </div>
      </header>

      {loading && <p className="meta">{t('data.loading')}</p>}
      {!loading && items.length === 0 && <p className="meta">{t('alerts.empty')}</p>}

      <div className="list">
        {items.map((item) => (
          <div className={`list-row level-${item.level}`} key={item.id}>
            <div className="level-badge">{item.level}</div>
            <div className="list-main">
              <div className="list-title">{item.title}</div>
              <div className="meta">
                {item.triggered_at} · {item.status}
                {item.summary ? ` · ${item.summary}` : ''}
              </div>
              {item.evidence?.[0] && (
                <div className="meta quote">“{item.evidence[0].quote}”</div>
              )}
            </div>
            {item.status === 'OPEN' && (
              <button className="chip" onClick={() => void ack(item.id)}>
                {t('alerts.ack')}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


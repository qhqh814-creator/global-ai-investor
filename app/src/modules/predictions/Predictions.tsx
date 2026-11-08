import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface Prediction {
  id: number;
  code: string;
  direction: string;
  horizon_days: number;
  confidence: number | null;
  model_id: string | null;
  start_date: string;
  start_price: number;
  status: string;
  end_date: string | null;
  actual_change_pct: number | null;
  hit: number | null;
}

interface Accuracy {
  total: number;
  hit: number;
  accuracy: number | null;
  avg_error: number | null;
  by_model: Array<{ model_id: string | null; total: number; hit: number; accuracy: number | null }>;
}

export default function Predictions() {
  const { t } = useTranslation();
  const [items, setItems] = useState<Prediction[]>([]);
  const [stats, setStats] = useState<Accuracy | null>(null);
  const [code, setCode] = useState('600000');
  const [direction, setDirection] = useState('UP');
  const [horizon, setHorizon] = useState(5);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    const [list, acc] = await Promise.all([
      apiGetRaw<{ items: Prediction[] }>('/api/predictions?limit=50'),
      apiGetRaw<Accuracy>('/api/accuracy')
    ]);
    setItems(list?.items ?? []);
    setStats(acc);
  };

  useEffect(() => {
    void load();
  }, []);

  const create = async () => {
    const res = await apiPost<{ id: number }>('/api/predictions', {
      code,
      direction,
      horizon_days: horizon,
      confidence: 0.6,
      model_id: 'manual'
    });
    setMessage(res?.id ? t('predictions.created') : t('predictions.createFailed'));
    await load();
  };

  const settle = async () => {
    const res = await apiPost<{ pending: number; settled: number }>('/api/predictions/settle');
    setMessage(`${t('predictions.settled')}: ${res?.settled ?? 0}/${res?.pending ?? 0}`);
    await load();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('predictions.title')}</h1>
          <p className="subtitle">{t('predictions.subtitle')}</p>
        </div>
        <button className="chip" onClick={() => void settle()}>{t('predictions.settle')}</button>
      </header>

      <div className="metric-grid">
        <div className="metric"><span>{t('predictions.total')}</span><b>{stats?.total ?? 0}</b></div>
        <div className="metric"><span>{t('predictions.hit')}</span><b>{stats?.hit ?? 0}</b></div>
        <div className="metric"><span>{t('predictions.accuracy')}</span><b>{stats?.accuracy != null ? `${(stats.accuracy * 100).toFixed(2)}%` : '—'}</b></div>
        <div className="metric"><span>{t('predictions.avgError')}</span><b>{stats?.avg_error != null ? `${(stats.avg_error * 100).toFixed(2)}%` : '—'}</b></div>
      </div>

      <div className="panel">
        <h2>{t('predictions.create')}</h2>
        <div className="row">
          <input className="input" value={code} onChange={(e) => setCode(e.target.value)} />
          <select className="input" value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="UP">UP</option>
            <option value="DOWN">DOWN</option>
            <option value="FLAT">FLAT</option>
          </select>
          <input className="input" type="number" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          <button className="chip primary" onClick={() => void create()}>{t('predictions.add')}</button>
        </div>
        {message && <p className="meta">{message}</p>}
      </div>

      <div className="panel">
        <h2>{t('predictions.list')}</h2>
        <table className="table">
          <thead>
            <tr>
              <th>#</th><th>{t('predictions.code')}</th><th>{t('predictions.direction')}</th>
              <th>{t('predictions.horizon')}</th><th>{t('predictions.start')}</th><th>{t('predictions.status')}</th>
              <th>{t('predictions.end')}</th><th>{t('predictions.hit')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td>{p.id}</td><td>{p.code}</td><td>{p.direction}</td><td>{p.horizon_days}</td>
                <td>{p.start_date} @ {p.start_price}</td>
                <td>{p.status}</td>
                <td>{p.end_date ?? '—'}</td>
                <td>{p.hit == null ? '—' : p.hit ? '✓' : '✗'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

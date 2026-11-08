import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface Plan {
  id: number;
  code: string;
  name: string | null;
  action: string;
  status: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  qty: number;
  position_value: number;
  risk_amount: number;
  risk_pct: number;
  confidence: number | null;
  market_regime: string;
  reason_summary: string | null;
  reasons: Array<{ type: string; text: string }>;
}

interface WeeklySim {
  sim: {
    id: number;
    name: string;
    start_date: string;
    initial_cash: number;
    cash: number;
    status: string;
    note: string | null;
  } | null;
  plans?: Array<{ id: number; code: string; entry_price: number | null; stop_loss: number | null; take_profit: number | null; qty: number; status: string }>;
  marks?: Array<{ trade_date: string; equity: number | null; benchmark_value: number | null }>;
  note?: string;
}

interface Regime {
  regime: string;
  up_ratio: number | null;
  size_factor: number;
  note: string;
  quote_time?: string | null;
}

export default function TradePlan() {
  const { t } = useTranslation();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [regime, setRegime] = useState<Regime | null>(null);
  const [weekly, setWeekly] = useState<WeeklySim | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    const [p, r, w] = await Promise.all([
      apiGetRaw<{ items: Plan[] }>('/api/trade-plans'),
      apiGetRaw<Regime>('/api/market/regime'),
      apiGetRaw<WeeklySim>('/api/weekly/latest')
    ]);
    setPlans(p?.items ?? []);
    setRegime(r);
    setWeekly(w);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const build = async () => {
    setMessage(t('tradeplan.building'));
    await apiPost('/api/trade-plans/run');
    await load();
    setMessage(t('tradeplan.built'));
  };

  const evaluate = async () => {
    setEvaluating(true);
    const res = await apiPost<{ status: string; total_return?: number | null; message?: string }>('/api/weekly/evaluate');
    setMessage(res ? `${res.status}${res.total_return != null ? ' · ' + (res.total_return * 100).toFixed(2) + '%' : ''} · ${res.message ?? ''}` : t('tradeplan.evalFailed'));
    await load();
    setEvaluating(false);
  };

  const start = async () => {
    const res = await apiPost<{ sim_id: number; start_date: string }>('/api/weekly/start', { initial_cash: 100000 });
    setMessage(res ? `${t('tradeplan.started')}: ${res.start_date}` : t('tradeplan.startFailed'));
    await load();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('tradeplan.title')}</h1>
          <p className="subtitle">{t('tradeplan.subtitle')}</p>
        </div>
        <div className="row">
          <button className="chip" onClick={() => void build()}>{t('tradeplan.build')}</button>
          <button className="chip" onClick={() => void evaluate()} disabled={evaluating}>{evaluating ? '…' : t('tradeplan.evaluate')}</button>
          <button className="chip primary" onClick={() => void start()}>{t('tradeplan.start')}</button>
        </div>
      </header>

      {message && <p className="meta">{message}</p>}
      {regime && (
        <div className="panel">
          <h2>{t('tradeplan.regime')}</h2>
          <p className="meta">
            {regime.regime} · {t('tradeplan.upRatio')} {regime.up_ratio ?? '—'} · {t('tradeplan.sizeFactor')} {regime.size_factor} · {regime.quote_time ?? ''}
          </p>
          <p className="meta">{regime.note}</p>
        </div>
      )}

      <div className="panel">
        <h2>{t('tradeplan.plans')}</h2>
        {loading && <p className="meta">{t('data.loading')}</p>}
        {!loading && plans.length === 0 && <p className="meta">{t('tradeplan.noPlans')}</p>}
        <table className="table">
          <thead>
            <tr>
              <th>{t('tradeplan.code')}</th><th>{t('tradeplan.action')}</th><th>{t('tradeplan.status')}</th>
              <th>{t('tradeplan.entry')}</th><th>{t('tradeplan.stop')}</th><th>{t('tradeplan.target')}</th>
              <th>{t('tradeplan.qty')}</th><th>{t('tradeplan.value')}</th><th>{t('tradeplan.risk')}</th><th>{t('tradeplan.regimeShort')}</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((p) => (
              <tr key={p.id}>
                <td>{p.name ?? '—'} <span className="meta">{p.code}</span></td>
                <td>{p.action}</td><td>{p.status}</td>
                <td>{p.entry_price ?? '—'}</td><td>{p.stop_loss ?? '—'}</td><td>{p.take_profit ?? '—'}</td>
                <td>{p.qty}</td><td>{p.position_value.toLocaleString()}</td><td>{(p.risk_pct * 100).toFixed(2)}%</td><td>{p.market_regime}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <h2>{t('tradeplan.weekly')}</h2>
        {weekly?.sim ? (
          <>
            <p className="meta">
              {weekly.sim.name} · {t('tradeplan.startDate')}: {weekly.sim.start_date} · {t('tradeplan.initialCash')}: {weekly.sim.initial_cash.toLocaleString()} · {t('tradeplan.status')}: {weekly.sim.status}
            </p>
            <p className="meta">{weekly.sim.note}</p>
            <p className="meta">{weekly.note}</p>
            {(weekly.marks ?? []).length > 0 && (
              <table className="table">
                <thead><tr><th>{t('tradeplan.date')}</th><th>{t('tradeplan.equity')}</th><th>{t('tradeplan.benchmark')}</th></tr></thead>
                <tbody>
                  {(weekly.marks ?? []).map((m) => (
                    <tr key={m.trade_date}><td>{m.trade_date}</td><td>{m.equity?.toLocaleString() ?? '—'}</td><td>{m.benchmark_value ?? '—'}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {(weekly.plans ?? []).length > 0 && (
              <table className="table">
                <thead>
                  <tr><th>{t('tradeplan.code')}</th><th>{t('tradeplan.entry')}</th><th>{t('tradeplan.stop')}</th><th>{t('tradeplan.target')}</th><th>{t('tradeplan.qty')}</th><th>{t('tradeplan.status')}</th></tr>
                </thead>
                <tbody>
                  {(weekly.plans ?? []).map((p) => (
                    <tr key={p.id}>
                      <td>{p.code}</td><td>{p.entry_price ?? '—'}</td><td>{p.stop_loss ?? '—'}</td>
                      <td>{p.take_profit ?? '—'}</td><td>{p.qty}</td><td>{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        ) : (
          <p className="meta">{t('tradeplan.noWeekly')}</p>
        )}
      </div>

      <p className="disclaimer">{t('tradeplan.disclaimer')}</p>
    </div>
  );
}


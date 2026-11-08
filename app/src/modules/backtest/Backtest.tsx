import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiPost } from '../../api/client';

interface Trade {
  code: string;
  side: string;
  trade_date: string;
  price: number;
  qty: number;
  fee_total: number;
  rule_version_id: string | null;
}

interface Metrics {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  trades_count: number;
  final_equity: number;
  equity_curve: Array<{ date: string; equity: number }>;
}

interface BacktestResult {
  backtest_id: number;
  status: string;
  metrics?: Metrics;
  trades?: Trade[];
  reason?: string;
}

function EquityCurve({ points }: { points: Array<{ date: string; equity: number }> }) {
  if (!points || points.length < 2) return null;
  const width = 760;
  const height = 160;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const path = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((p.equity - min) / span) * (height - 12) - 6;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg className="equity" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" />
    </svg>
  );
}

export default function Backtest() {
  const { t } = useTranslation();
  const [codes, setCodes] = useState('600000,300001,688001');
  const [start, setStart] = useState('2026-01-01');
  const [end, setEnd] = useState('2026-11-07');
  const [entryPct, setEntryPct] = useState(5);
  const [holdDays, setHoldDays] = useState(3);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [running, setRunning] = useState(false);

  const run = async () => {
    setRunning(true);
    const res = await apiPost<BacktestResult>('/api/backtest/run', {
      codes: codes.split(',').map((c) => c.trim()).filter(Boolean),
      start_date: start,
      end_date: end,
      initial_cash: 1000000,
      entry_pct: entryPct,
      hold_days: holdDays,
      max_positions: 3
    });
    setResult(res);
    setRunning(false);
  };

  const m = result?.metrics;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('backtest.title')}</h1>
          <p className="subtitle">{t('backtest.subtitle')}</p>
        </div>
      </header>

      <div className="panel">
        <div className="form-grid">
          <label>
            {t('backtest.codes')}
            <input className="input wide" value={codes} onChange={(e) => setCodes(e.target.value)} />
          </label>
          <label>
            {t('backtest.start')}
            <input className="input" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            {t('backtest.end')}
            <input className="input" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <label>
            {t('backtest.entryPct')}
            <input className="input" type="number" value={entryPct} onChange={(e) => setEntryPct(Number(e.target.value))} />
          </label>
          <label>
            {t('backtest.holdDays')}
            <input className="input" type="number" value={holdDays} onChange={(e) => setHoldDays(Number(e.target.value))} />
          </label>
        </div>
        <button className="chip primary" onClick={() => void run()} disabled={running}>
          {running ? '…' : t('backtest.run')}
        </button>
      </div>

      {result && result.status !== 'DONE' && (
        <div className="panel">
          <p className="meta">{result.status}: {result.reason ?? ''}</p>
        </div>
      )}

      {m && (
        <>
          <div className="metric-grid">
            <div className="metric"><span>{t('backtest.totalReturn')}</span><b>{(m.total_return * 100).toFixed(2)}%</b></div>
            <div className="metric"><span>{t('backtest.maxDrawdown')}</span><b>{(m.max_drawdown * 100).toFixed(2)}%</b></div>
            <div className="metric"><span>{t('backtest.winRate')}</span><b>{(m.win_rate * 100).toFixed(2)}%</b></div>
            <div className="metric"><span>{t('backtest.trades')}</span><b>{m.trades_count}</b></div>
            <div className="metric"><span>{t('backtest.finalEquity')}</span><b>{m.final_equity.toLocaleString()}</b></div>
          </div>
          <div className="panel">
            <h2>{t('backtest.equityCurve')}</h2>
            <EquityCurve points={m.equity_curve} />
          </div>
          <div className="panel">
            <h2>{t('backtest.tradeList')}</h2>
            <table className="table">
              <thead>
                <tr>
                  <th>{t('backtest.date')}</th><th>{t('backtest.side')}</th><th>{t('backtest.code')}</th>
                  <th>{t('backtest.price')}</th><th>{t('backtest.qty')}</th><th>{t('backtest.fee')}</th><th>{t('backtest.ruleVersion')}</th>
                </tr>
              </thead>
              <tbody>
                {(result?.trades ?? []).slice(0, 40).map((tr, i) => (
                  <tr key={i}>
                    <td>{tr.trade_date}</td><td>{tr.side}</td><td>{tr.code}</td>
                    <td>{tr.price}</td><td>{tr.qty}</td><td>{tr.fee_total}</td><td>{tr.rule_version_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

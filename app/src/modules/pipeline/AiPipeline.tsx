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
  reason_summary: string | null;
}

interface PipelineStatus {
  news_count: number;
  announcement_count: number;
  last_news_at: string | null;
  last_announcement_at: string | null;
  analyzed_count: number;
  pending_analysis: number;
  failed_tasks: number;
  market_regime: { regime: string; up_ratio: number | null; note: string };
  opportunities: Plan[];
  recos: Array<{ id: number; reco_type: string; code: string; name: string | null; action: string }>;
  weekly: {
    sim: { start_date: string; initial_cash: number; status: string; note: string | null } | null;
    plans?: Array<{ code: string; entry_price: number | null; stop_loss: number | null; take_profit: number | null; qty: number; status: string }>;
    marks?: Array<{ trade_date: string; equity: number | null; benchmark_value: number | null }>;
    note?: string;
  } | null;
}

interface StageResult {
  key: string;
  status: string;
  detail: unknown;
}

export default function AiPipeline() {
  const { t } = useTranslation();
  const [data, setData] = useState<PipelineStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [evaluating, setEvaluating] = useState(false);
  const [stages, setStages] = useState<StageResult[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    const res = await apiGetRaw<PipelineStatus>('/api/pipeline/status');
    setData(res);
  };

  useEffect(() => {
    void load();
  }, []);

  const runAll = async () => {
    setRunning(true);
    setMessage(t('pipeline.running'));
    const res = await apiPost<PipelineStatus & { stages: StageResult[] }>('/api/pipeline/run?collect=true&analyze_limit=6');
    setStages(res?.stages ?? []);
    setData(res);
    setMessage(t('pipeline.done'));
    setRunning(false);
  };

  const evaluate = async () => {
    setEvaluating(true);
    const res = await apiPost<{ status: string; total_return?: number | null; message?: string }>('/api/weekly/evaluate');
    setMessage(res ? `${res.status}${res.total_return != null ? ' · ' + (res.total_return * 100).toFixed(2) + '%' : ''} · ${res.message ?? ''}` : t('pipeline.evalFailed'));
    await load();
    setEvaluating(false);
  };

  const week = data?.weekly?.sim;
  const marks = data?.weekly?.marks ?? [];
  const finalMark = marks.length ? marks[marks.length - 1] : null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('pipeline.title')}</h1>
          <p className="subtitle">{t('pipeline.subtitle')}</p>
        </div>
        <div className="row">
          <button className="chip primary" onClick={() => void runAll()} disabled={running}>
            {running ? '…' : t('pipeline.runAll')}
          </button>
          <button className="chip" onClick={() => void evaluate()} disabled={evaluating || !week}>
            {evaluating ? '…' : t('pipeline.evaluate')}
          </button>
        </div>
      </header>

      {message && <p className="meta">{message}</p>}
      {!data && <p className="meta">{t('data.loading')}</p>}

      {data && (
        <>
          <div className="panel">
            <h2>{t('pipeline.step1')}</h2>
            <p className="meta">
              {t('pipeline.news')}: {data.news_count} · {t('pipeline.lastNews')}: {data.last_news_at ?? '—'} ·{' '}
              {t('pipeline.announcements')}: {data.announcement_count} · {t('pipeline.lastAnn')}: {data.last_announcement_at ?? '—'}
            </p>
            <p className="meta">{t('pipeline.step1Hint')}</p>
          </div>

          <div className="panel">
            <h2>{t('pipeline.step2')}</h2>
            <p className="meta">
              {t('pipeline.analyzed')}: {data.analyzed_count} · {t('pipeline.pending')}: {data.pending_analysis} · {t('pipeline.failed')}: {data.failed_tasks}
            </p>
            <p className="meta">{t('pipeline.step2Hint')}</p>
          </div>

          <div className="panel">
            <h2>{t('pipeline.step3')}</h2>
            <p className="meta">
              {t('pipeline.regime')}: {data.market_regime.regime} · {t('pipeline.upRatio')}: {data.market_regime.up_ratio ?? '—'}
            </p>
            <p className="meta">{data.market_regime.note}</p>
            {data.opportunities.length === 0 && <p className="meta">{t('pipeline.noOpportunity')}</p>}
            {data.opportunities.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('pipeline.code')}</th><th>{t('pipeline.action')}</th><th>{t('pipeline.status')}</th>
                    <th>{t('pipeline.entry')}</th><th>{t('pipeline.stop')}</th><th>{t('pipeline.target')}</th>
                    <th>{t('pipeline.qty')}</th><th>{t('pipeline.space')}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.opportunities.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name ?? '—'} <span className="meta">{p.code}</span></td>
                      <td>{p.action}</td><td>{p.status}</td>
                      <td>{p.entry_price ?? '—'}</td><td>{p.stop_loss ?? '—'}</td><td>{p.take_profit ?? '—'}</td>
                      <td>{p.qty}</td>
                      <td>{p.reason_summary ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="meta">{t('pipeline.step3Hint')}</p>
          </div>

          <div className="panel">
            <h2>{t('pipeline.step4')}</h2>
            {week ? (
              <>
                <p className="meta">
                  {t('pipeline.startDate')}: {week.start_date} · {t('pipeline.initialCash')}: {week.initial_cash.toLocaleString()} · {t('pipeline.simStatus')}: {week.status}
                </p>
                <p className="meta">{week.note}</p>
                <p className="meta">{t('pipeline.step4Hint')}</p>
                {(data.weekly?.plans ?? []).length > 0 && (
                  <table className="table">
                    <thead><tr><th>{t('pipeline.code')}</th><th>{t('pipeline.entry')}</th><th>{t('pipeline.stop')}</th><th>{t('pipeline.target')}</th><th>{t('pipeline.qty')}</th><th>{t('pipeline.status')}</th></tr></thead>
                    <tbody>
                      {(data.weekly?.plans ?? []).map((p, i) => (
                        <tr key={`${p.code}-${i}`}>
                          <td>{p.code}</td><td>{p.entry_price ?? '—'}</td><td>{p.stop_loss ?? '—'}</td>
                          <td>{p.take_profit ?? '—'}</td><td>{p.qty}</td><td>{p.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            ) : (
              <p className="meta">{t('pipeline.noSim')}</p>
            )}
          </div>

          <div className="panel">
            <h2>{t('pipeline.step5')}</h2>
            {finalMark ? (
              <p className="meta">
                {finalMark.trade_date} · {t('pipeline.equity')}: {finalMark.equity?.toLocaleString() ?? '—'} · {t('pipeline.benchmark')}: {finalMark.benchmark_value ?? '—'}
              </p>
            ) : (
              <p className="meta">{t('pipeline.weekPending')}</p>
            )}
          </div>

          {stages.length > 0 && (
            <div className="panel">
              <h2>{t('pipeline.stageResults')}</h2>
              {stages.map((s) => (
                <p className="meta" key={s.key}>
                  {s.key}: {s.status}
                </p>
              ))}
            </div>
          )}
        </>
      )}

      <p className="disclaimer">{t('pipeline.disclaimer')}</p>
    </div>
  );
}

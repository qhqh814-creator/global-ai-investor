import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface Evidence {
  analysis_id: number;
  title: string | null;
  url: string | null;
  published_at: string | null;
  source_id: string | null;
  event_type: string;
  sentiment: string;
  materiality: string;
  summary: string;
  quotes: Array<{ quote: string; source_url: string; published_at?: string | null }>;
  model_id: string | null;
}

interface Reco {
  id: number;
  reco_type: string;
  trade_date: string;
  code: string;
  name: string | null;
  action: string;
  confidence: number | null;
  score: number | null;
  horizon_days: number | null;
  reason_summary: string | null;
  reasons: Array<{ type: string; text: string; analysis_id?: number }>;
  evidence: Evidence[];
  quote: {
    last: number | null;
    change_pct: number | null;
    quote_time: string | null;
    source_id: string;
    is_realtime: number;
    license_status: string;
  } | null;
  position: { qty: number; sellable_qty: number; avg_cost: number; buy_date: string } | null;
  model_id: string | null;
  created_at: string;
}

function actionClass(action: string): string {
  if (action === 'SELL' || action === 'REDUCE') return 'sell';
  if (action === 'BUY_CANDIDATE' || action === 'BUY') return 'buy';
  return '';
}

function RecoCard({ reco }: { reco: Reco }) {
  const { t } = useTranslation();
  const q = reco.quote;
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="list-title">
          <b>{reco.name ?? '—'}</b> <span className="meta">{reco.code}</span>
        </div>
        <div className={`level-badge ${actionClass(reco.action)}`}>{reco.action}</div>
      </div>
      <div className="meta" style={{ marginTop: 6 }}>
        {t('aiadvice.confidence')}: {(reco.confidence ?? 0) * 100}% · {t('aiadvice.model')}: {reco.model_id ?? '—'} · {reco.trade_date}
        {reco.horizon_days ? ` · ${t('aiadvice.horizon')}: ${reco.horizon_days}d` : ''}
      </div>
      {reco.reason_summary && <p className="meta" style={{ marginTop: 8 }}>{reco.reason_summary}</p>}

      <div className="list" style={{ marginTop: 10 }}>
        {reco.reasons.map((r, i) => (
          <div className="list-row" key={i}>
            <div className="list-main">
              <div className="meta">{r.type}</div>
              <div>{r.text}</div>
            </div>
          </div>
        ))}
      </div>

      {q && (
        <p className="meta" style={{ marginTop: 8 }}>
          {t('aiadvice.last')}: {q.last ?? '—'} ({q.change_pct ?? '—'}%) · {t('aiadvice.quoteTime')}: {q.quote_time ?? '—'} ·
          {' '}{q.source_id} · {q.is_realtime ? 'realtime' : t('aiadvice.notRealtime')} · {q.license_status}
        </p>
      )}
      {reco.position && (
        <p className="meta">
          {t('aiadvice.position')}: {reco.position.qty} ({t('aiadvice.sellable')} {reco.position.sellable_qty}) ·
          {' '}{t('aiadvice.cost')}: {reco.position.avg_cost}
        </p>
      )}

      {reco.evidence.length > 0 && (
        <div className="panel" style={{ marginTop: 12, marginBottom: 0 }}>
          <h2 style={{ fontSize: 13 }}>{t('aiadvice.evidence')}</h2>
          {reco.evidence.map((ev, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div>
                {ev.url ? (
                  <a href={ev.url} target="_blank" rel="noreferrer">
                    [{ev.materiality}] {ev.title ?? ev.url}
                  </a>
                ) : (
                  <span>[{ev.materiality}] {ev.title ?? '—'}</span>
                )}
              </div>
              <div className="meta">
                {ev.source_id} · {ev.published_at ?? '—'} · {ev.event_type} · {ev.model_id ?? '—'}
              </div>
              {ev.quotes.map((quote, j) => (
                <div className="meta quote" key={j}>“{quote.quote}”</div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AiAdvice() {
  const { t } = useTranslation();
  const [buys, setBuys] = useState<Reco[]>([]);
  const [holds, setHolds] = useState<Reco[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = async () => {
    const [b, h] = await Promise.all([
      apiGetRaw<{ items: Reco[] }>('/api/ai/recommendations?reco_type=BUY'),
      apiGetRaw<{ items: Reco[] }>('/api/ai/recommendations?reco_type=HOLDING')
    ]);
    setBuys(b?.items ?? []);
    setHolds(h?.items ?? []);
    setLoading(false);
  };

  useEffect(() => {
    void load();
  }, []);

  const run = async () => {
    setRunning(true);
    await apiPost('/api/ai/recommendations/run');
    await load();
    setRunning(false);
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('aiadvice.title')}</h1>
          <p className="subtitle">{t('aiadvice.subtitle')}</p>
        </div>
        <button className="chip primary" onClick={() => void run()} disabled={running}>
          {running ? '…' : t('aiadvice.run')}
        </button>
      </header>

      {loading && <p className="meta">{t('data.loading')}</p>}

      <div className="panel">
        <h2>{t('aiadvice.buySection')}</h2>
        {buys.length === 0 && <p className="meta">{t('aiadvice.emptyBuy')}</p>}
        <div className="list">
          {buys.map((reco) => (
            <RecoCard key={reco.id} reco={reco} />
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>{t('aiadvice.holdSection')}</h2>
        {holds.length === 0 && <p className="meta">{t('aiadvice.emptyHold')}</p>}
        <div className="list">
          {holds.map((reco) => (
            <RecoCard key={reco.id} reco={reco} />
          ))}
        </div>
      </div>

      <p className="disclaimer">{t('aiadvice.disclaimer')}</p>
    </div>
  );
}


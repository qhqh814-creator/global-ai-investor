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

interface TeamReview {
  code: string;
  as_of: string;
  review: {
    rating: string;
    confidence: number;
    summary: string;
    technical_view: string;
    news_view: string;
    risk_view: string;
    entry_price: number | null;
    target_price: number | null;
    stop_loss: number | null;
    reasons: string[];
    risks: string[];
    evidence: Array<{ quote: string; source?: string }>;
  };
  indicators: {
    trend?: string;
    rsi14?: number | null;
    ma20?: number | null;
    macd_state?: string;
    volume_ratio?: number | null;
    as_of?: string;
  };
  model_id: string | null;
}

function actionClass(action: string): string {
  if (action === 'SELL' || action === 'REDUCE') return 'sell';
  if (action === 'BUY_CANDIDATE' || action === 'BUY') return 'buy';
  return '';
}

function TeamPanel({ team }: { team: TeamReview }) {
  const { t } = useTranslation();
  return (
    <div className="panel" style={{ marginTop: 10, marginBottom: 0 }}>
      <h2 style={{ fontSize: 13 }}>{t('aiadvice.teamTitle')}</h2>
      <p className="meta">
        {t('aiadvice.teamRating')}: <b>{team.review.rating}</b> · {t('aiadvice.teamConfidence')}: {(team.review.confidence * 100).toFixed(0)}% ·
        {' '}{team.as_of} · {team.model_id ?? '—'}
      </p>
      <p className="meta">{team.review.summary}</p>
      {team.review.technical_view && <p className="meta">{t('aiadvice.teamTech')}: {team.review.technical_view}</p>}
      {team.review.news_view && <p className="meta">{t('aiadvice.teamNews')}: {team.review.news_view}</p>}
      {team.review.risk_view && <p className="meta">{t('aiadvice.teamRisk')}: {team.review.risk_view}</p>}
      <p className="meta">
        {t('aiadvice.teamEntry')}: {team.review.entry_price ?? '—'} · {t('aiadvice.teamTarget')}: {team.review.target_price ?? '—'} ·
        {' '}{t('aiadvice.teamStop')}: {team.review.stop_loss ?? '—'}
      </p>
      <p className="meta">
        MA20: {team.indicators?.ma20 ?? '—'} · RSI: {team.indicators?.rsi14 ?? '—'} · MACD: {team.indicators?.macd_state ?? '—'} ·
        {' '}量比: {team.indicators?.volume_ratio ?? '—'} · 趋势: {team.indicators?.trend ?? '—'}
      </p>
      {(team.review.reasons ?? []).length > 0 && (
        <p className="meta">{t('aiadvice.teamReasons')}: {(team.review.reasons ?? []).join('；')}</p>
      )}
      {(team.review.risks ?? []).length > 0 && (
        <p className="meta">{t('aiadvice.teamRisks')}: {(team.review.risks ?? []).join('；')}</p>
      )}
      {(team.review.evidence ?? []).length > 0 && (
        <div className="meta">
          {t('aiadvice.teamEvidence')}:
          {(team.review.evidence ?? []).map((e, i) => (
            <div key={i} className="quote">“{e.quote}”</div>
          ))}
        </div>
      )}
    </div>
  );
}

function RecoCard({ reco, team, onTeam, busy }: { reco: Reco; team: TeamReview | null; onTeam: () => void; busy: boolean }) {
  const { t } = useTranslation();
  const q = reco.quote;
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <div className="list-title">
          <b>{reco.name ?? '—'}</b> <span className="meta">{reco.code}</span>
        </div>
        <div className="row" style={{ alignItems: 'center' }}>
          <button className="chip" onClick={onTeam} disabled={busy}>{busy ? '…' : t('aiadvice.teamRun')}</button>
          <div className={`level-badge ${actionClass(reco.action)}`}>{reco.action}</div>
        </div>
      </div>
      <div className="meta" style={{ marginTop: 6 }}>
        {t('aiadvice.confidence')}: {(reco.confidence ?? 0) * 100}% · {t('aiadvice.model')}: {reco.model_id ?? '—'} · {reco.trade_date}
        {reco.horizon_days ? ` · ${t('aiadvice.horizon')}: ${reco.horizon_days}d` : ''}
      </div>
      {reco.reason_summary && <p className="meta" style={{ marginTop: 8 }}>{reco.reason_summary}</p>}

      {team && <TeamPanel team={team} />}

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
  const [teams, setTeams] = useState<Record<string, TeamReview | null>>({});
  const [teamBusy, setTeamBusy] = useState<string | null>(null);
  const [teamError, setTeamError] = useState<string | null>(null);

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

  const runTeam = async (code: string) => {
    setTeamBusy(code);
    setTeamError(null);
    try {
      const res = await apiPost<TeamReview>(`/api/ai/team-review?code=${code}`);
      setTeams((prev) => ({ ...prev, [code]: res }));
    } catch (e) {
      setTeamError(e instanceof Error ? e.message : String(e));
    } finally {
      setTeamBusy(null);
    }
  };

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
      {teamError && <p className="meta">{t('aiadvice.teamError')}: {teamError}</p>}

      <div className="panel">
        <h2>{t('aiadvice.buySection')}</h2>
        {buys.length === 0 && <p className="meta">{t('aiadvice.emptyBuy')}</p>}
        <div className="list">
          {buys.map((reco) => (
            <RecoCard
              key={reco.id}
              reco={reco}
              team={teams[reco.code] ?? null}
              busy={teamBusy === reco.code}
              onTeam={() => void runTeam(reco.code)}
            />
          ))}
        </div>
      </div>

      <div className="panel">
        <h2>{t('aiadvice.holdSection')}</h2>
        {holds.length === 0 && <p className="meta">{t('aiadvice.emptyHold')}</p>}
        <div className="list">
          {holds.map((reco) => (
            <RecoCard
              key={reco.id}
              reco={reco}
              team={teams[reco.code] ?? null}
              busy={teamBusy === reco.code}
              onTeam={() => void runTeam(reco.code)}
            />
          ))}
        </div>
      </div>

      <p className="disclaimer">{t('aiadvice.disclaimer')}</p>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import DataCard from '../../components/DataCard';
import { apiGetRaw, getBackend, type DashboardCard } from '../../api/client';

const CARD_KEYS = [
  'sse_index',
  'szse_index',
  'chinext_index',
  'star50',
  'bse50',
  'market_overview',
  'breadth',
  'limit_counts',
  'turnover',
  'good_news',
  'risk_alerts',
  'ai_opportunities',
  'watchlist',
  'signals',
  'paper_account'
] as const;

const SHORT_TO_I18N: Record<string, string> = {
  sse_index: 'sse_index',
  szse_index: 'szse_index',
  chinext_index: 'chinext_index',
  star50: 'star50',
  bse50: 'bse50',
  market_overview: 'market_overview',
  breadth: 'breadth',
  limit_counts: 'limit_counts',
  turnover: 'turnover',
  good_news: 'good_news',
  risk_alerts: 'risk_alerts',
  ai_opportunities: 'ai_opportunities',
  watchlist: 'watchlist',
  signals: 'signals',
  paper_account: 'paper_account'
};

function reasonText(t: (key: string) => string, reason: string | null): string {
  if (!reason) return '';
  const known = t(`data.reason.${reason}`);
  return known === `data.reason.${reason}` ? reason : known;
}

export default function Dashboard() {
  const { t } = useTranslation();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);
  const [cards, setCards] = useState<DashboardCard[] | null>(null);

  useEffect(() => {
    void (async () => {
      const backend = await getBackend();
      setBackendOk(backend != null);
      const data = backend ? await apiGetRaw<{ cards: DashboardCard[] }>('/api/dashboard') : null;
      setCards(data?.cards ?? null);
    })();
  }, []);

  const byKey = new Map((cards ?? []).map((c) => [c.key.replace('dashboard.', ''), c]));
  const CARD_KEY_ALIAS: Record<string, string> = { breadth: 'market_breadth' };
  const resolveKey = (k: string) => CARD_KEY_ALIAS[k] ?? k;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('dashboard.title')}</h1>
          <p className="subtitle">{t('dashboard.subtitle')}</p>
        </div>
        <div className={backendOk ? 'status ok' : 'status warn'}>
          {t('dashboard.backend')}:{' '}
          {backendOk == null
            ? '…'
            : backendOk
              ? t('dashboard.backendRunning')
              : t('dashboard.backendFailed')}
        </div>
      </header>

      <div className="grid">
        {CARD_KEYS.map((shortKey) => {
          const key = shortKey;
          const card = byKey.get(resolveKey(key));
          return (
            <DataCard
              key={key}
              title={t(`dashboard.cards.${SHORT_TO_I18N[key] ?? key}`)}
              value={card?.status === 'available' ? card.value : null}
              provenance={card?.provenance ?? null}
              status={card?.status === 'available' ? 'available' : 'unavailable'}
              reason={card?.status === 'unavailable' ? reasonText((k) => String(t(k)), card.reason) : undefined}
            />
          );
        })}
      </div>
    </div>
  );
}




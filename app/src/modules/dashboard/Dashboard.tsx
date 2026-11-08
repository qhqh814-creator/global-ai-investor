import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import DataCard from '../../components/DataCard';
import { getBackend } from '../../api/client';

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

export default function Dashboard() {
  const { t } = useTranslation();
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  useEffect(() => {
    void getBackend().then((b) => setBackendOk(b != null));
  }, []);

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
        {CARD_KEYS.map((key) => (
          <DataCard key={key} title={t(`dashboard.cards.${key}`)} status="unavailable" />
        ))}
      </div>
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import type { Provenance } from '../api/client';

interface Props {
  title: string;
  value?: string | null;
  provenance?: Provenance | null;
  status?: 'available' | 'unavailable' | 'loading';
  reason?: string;
}

export default function DataCard({ title, value, provenance, status = 'unavailable', reason }: Props) {
  const { t } = useTranslation();
  const isAvailable = status === 'available' && value != null;
  const isLocal = provenance?.sourceIds?.includes('local_engine') ?? false;

  return (
    <section className={isAvailable ? 'card available' : 'card unavailable'}>
      <header className="card-title">{title}</header>
      {status === 'loading' && <div className="card-value muted">{t('data.loading')}</div>}
      {status !== 'loading' && isAvailable && (
        <>
          <div className="card-value">{value}</div>
          <div className="card-meta">
            <span className="badge">{isLocal ? t('provenance.local') : provenance?.isRealtime ? t('provenance.licensed') : t('provenance.thirdParty')}</span>
            {provenance?.quoteTime && (
              <span className="meta">
                {t('provenance.time')}: {provenance.quoteTime}
              </span>
            )}
            <span className="meta">
              {t('provenance.source')}: {provenance?.sourceIds?.join(', ') ?? '—'}
            </span>
          </div>
        </>
      )}
      {status === 'unavailable' && (
        <div className="card-unavailable">
          <div className="card-value muted">{t('data.unavailable')}</div>
          <div className="card-meta">
            <span className="meta">{reason ?? t('data.no_data')}</span>
          </div>
        </div>
      )}
    </section>
  );
}


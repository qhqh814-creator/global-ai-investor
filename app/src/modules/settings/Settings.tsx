import { useTranslation } from 'react-i18next';

export default function Settings() {
  const { t, i18n } = useTranslation();

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('settings.title')}</h1>
        </div>
      </header>

      <div className="panel">
        <h2>{t('settings.language')}</h2>
        <div className="row">
          <button className={i18n.language === 'zh-CN' ? 'chip active' : 'chip'} onClick={() => void i18n.changeLanguage('zh-CN')}>
            中文
          </button>
          <button className={i18n.language === 'en-US' ? 'chip active' : 'chip'} onClick={() => void i18n.changeLanguage('en-US')}>
            English
          </button>
        </div>
      </div>

      <div className="panel">
        <h2>{t('settings.backup')}</h2>
        <p className="meta">{t('settings.backupHint')}</p>
      </div>

      <div className="panel">
        <h2>{t('settings.datasources')}</h2>
        <p className="meta">P2 阶段接入（见 docs/04-数据源清单）。</p>
      </div>

      <div className="panel">
        <h2>{t('settings.about')}</h2>
        <p className="meta">
          {t('settings.version')}: v{__APP_VERSION__}
        </p>
        <p className="disclaimer">{t('settings.disclaimer')}</p>
      </div>
    </div>
  );
}

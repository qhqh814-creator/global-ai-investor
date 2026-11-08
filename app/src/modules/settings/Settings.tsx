import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

export default function Settings() {
  const { t, i18n } = useTranslation();
  const [deepseek, setDeepseek] = useState<boolean | null>(null);
  const [ollama, setOllama] = useState<boolean | null>(null);
  const [key, setKey] = useState('');
  const [message, setMessage] = useState<string | null>(null);

  const check = async () => {
    const [d, o] = await Promise.all([
      apiGetRaw<{ available: boolean }>('/api/ai/status?provider=deepseek'),
      apiGetRaw<{ available: boolean }>('/api/ai/status?provider=ollama')
    ]);
    setDeepseek(d?.available ?? null);
    setOllama(o?.available ?? null);
  };

  useEffect(() => {
    void check();
  }, []);

  const saveKey = async () => {
    if (!key.trim()) return;
    const res = await apiPost<{ ok: boolean }>('/api/settings/ai-key', { provider: 'deepseek', key: key.trim() });
    setMessage(res?.ok ? t('settings.aiKeySaved') : t('settings.aiKeyFailed'));
    setKey('');
    await check();
  };

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
        <h2>{t('settings.ai')}</h2>
        <p className="meta">
          DeepSeek: {deepseek == null ? '…' : deepseek ? t('settings.aiAvailable') : t('settings.aiUnavailable')} ·{' '}
          Ollama: {ollama == null ? '…' : ollama ? t('settings.aiAvailable') : t('settings.aiUnavailable')}
        </p>
        <p className="meta">{t('settings.aiKeyHint')}</p>
        <div className="row" style={{ marginTop: 8 }}>
          <input
            className="input wide"
            type="password"
            value={key}
            placeholder={t('settings.aiKeyPlaceholder')}
            onChange={(e) => setKey(e.target.value)}
          />
          <button className="chip primary" onClick={() => void saveKey()}>
            {t('settings.save')}
          </button>
        </div>
        {message && <p className="meta">{message}</p>}
      </div>

      <div className="panel">
        <h2>{t('settings.backup')}</h2>
        <p className="meta">{t('settings.backupHint')}</p>
      </div>

      <div className="panel">
        <h2>{t('settings.datasources')}</h2>
        <p className="meta">{t('settings.datasourceHint')}</p>
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

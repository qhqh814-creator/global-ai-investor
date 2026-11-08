import { useTranslation } from 'react-i18next';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import Dashboard from './modules/dashboard/Dashboard';
import Settings from './modules/settings/Settings';

const NAV = [
  { to: '/', key: 'nav.dashboard' },
  { to: '/settings', key: 'nav.settings' }
];

export default function App() {
  const { t, i18n } = useTranslation();
  const loc = useLocation();

  const toggleLang = () => void i18n.changeLanguage(i18n.language === 'zh-CN' ? 'en-US' : 'zh-CN');

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">{t('app.title')}</div>
        <div className="brand-sub">{t('app.subtitle')}</div>
        <nav>
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className={loc.pathname === n.to ? 'nav active' : 'nav'}>
              {t(n.key)}
            </Link>
          ))}
        </nav>
        <button className="lang" onClick={toggleLang}>
          {i18n.language === 'zh-CN' ? 'English' : '中文'}
        </button>
        <div className="version">v{__APP_VERSION__}</div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

import { useTranslation } from 'react-i18next';
import { Link, Route, Routes, useLocation } from 'react-router-dom';
import Dashboard from './modules/dashboard/Dashboard';
import News from './modules/news/News';
import Alerts from './modules/alerts/Alerts';
import Watchlist from './modules/watchlist/Watchlist';
import Signals from './modules/signals/Signals';
import Backtest from './modules/backtest/Backtest';
import Paper from './modules/paper/Paper';
import Predictions from './modules/predictions/Predictions';
import AiAdvice from './modules/aiadvice/AiAdvice';
import Settings from './modules/settings/Settings';

const NAV = [
  { to: '/', key: 'nav.dashboard' },
  { to: '/news', key: 'nav.news' },
  { to: '/alerts', key: 'nav.alerts' },
  { to: '/watchlist', key: 'nav.watchlist' },
  { to: '/signals', key: 'nav.signals' },
  { to: '/aiadvice', key: 'nav.aiadvice' },
  { to: '/backtest', key: 'nav.backtest' },
  { to: '/paper', key: 'nav.paper' },
  { to: '/predictions', key: 'nav.predictions' },
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
          <Route path="/news" element={<News />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/aiadvice" element={<AiAdvice />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/paper" element={<Paper />} />
          <Route path="/predictions" element={<Predictions />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

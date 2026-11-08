import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw } from '../../api/client';

interface NewsItem {
  id: number;
  source_id: string;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  license_status: string;
}

interface GlobalItem {
  id: number;
  source_id: string;
  title: string;
  url: string;
  summary: string | null;
  published_at: string | null;
  language: string;
  keywords: string | null;
  license_status: string;
  source_authenticity: string | null;
  price_reaction: string | null;
}

interface AnnouncementItem {
  id: number;
  sec_code: string | null;
  sec_name: string | null;
  title: string;
  published_at: string | null;
  url: string | null;
  file_type: string | null;
}

export default function News() {
  const { t } = useTranslation();
  const [news, setNews] = useState<NewsItem[]>([]);
  const [anns, setAnns] = useState<AnnouncementItem[]>([]);
  const [globals, setGlobals] = useState<GlobalItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      const [n, a, g] = await Promise.all([
        apiGetRaw<{ items: NewsItem[] }>('/api/news?limit=30'),
        apiGetRaw<{ items: AnnouncementItem[] }>('/api/announcements?limit=30'),
        apiGetRaw<{ items: GlobalItem[] }>('/api/global-news?limit=30')
      ]);
      setNews(n?.items ?? []);
      setAnns(a?.items ?? []);
      setGlobals(g?.items ?? []);
      setLoading(false);
    })();
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('news.title')}</h1>
          <p className="subtitle">{t('news.subtitle')}</p>
        </div>
      </header>

      {loading && <p className="meta">{t('data.loading')}</p>}

      <div className="two-col">
        <section className="panel">
          <h2>{t('news.announcements')}</h2>
          <div className="list">
            {anns.length === 0 && <p className="meta">{t('news.empty')}</p>}
            {anns.map((item) => (
              <div className="list-row" key={`a-${item.id}`}>
                <div className="list-main">
                  <a href={item.url ?? '#'} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                  <div className="meta">
                    {item.sec_code} {item.sec_name} · {item.published_at ?? '—'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>{t('news.news')}</h2>
          <div className="list">
            {news.length === 0 && <p className="meta">{t('news.empty')}</p>}
            {news.map((item) => (
              <div className="list-row" key={`n-${item.id}`}>
                <div className="list-main">
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                  <div className="meta">
                    {item.source_id} · {item.published_at ?? '—'}
                    {item.summary ? ` · ${item.summary}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="panel">
        <h2>{t('news.global')}</h2>
        <p className="meta">{t('news.globalHint')}</p>
        {globals.length === 0 && <p className="meta">{t('news.empty')}</p>}
        <div className="list">
          {globals.map((item) => (
            <div className="list-row" key={`g-${item.id}`}>
              <div className="list-main">
                <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
                <div className="meta">
                  {item.source_id} · {item.published_at ?? '—'} · {item.license_status}
                  {item.source_authenticity ? ` · ${item.source_authenticity}` : ''}
                  {item.price_reaction ? ` · ${item.price_reaction}` : ''}
                  {item.keywords ? ` · ${item.keywords}` : ''}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}


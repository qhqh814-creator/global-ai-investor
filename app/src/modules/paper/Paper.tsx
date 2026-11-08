import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiGetRaw, apiPost } from '../../api/client';

interface Position {
  code: string;
  name: string | null;
  qty: number;
  sellable_qty: number;
  avg_cost: number;
  last: number | null;
  pnl: number;
  quote_time: string | null;
}

interface Account {
  account: { name: string; initial_cash: number; cash: number };
  positions: Position[];
  total_asset: number;
  market_value: number;
  pnl: number;
}

interface Order {
  id: number;
  code: string;
  side: string;
  order_type: string;
  price: number | null;
  qty: number;
  status: string;
  reject_reason: string | null;
  created_at: string;
}

export default function Paper() {
  const { t } = useTranslation();
  const [account, setAccount] = useState<Account | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [code, setCode] = useState('600000');
  const [side, setSide] = useState('BUY');
  const [qty, setQty] = useState(100);
  const [message, setMessage] = useState<string | null>(null);

  const load = async () => {
    const [acc, ord] = await Promise.all([
      apiGetRaw<Account>('/api/paper/account'),
      apiGetRaw<{ items: Order[] }>('/api/paper/orders?limit=20')
    ]);
    setAccount(acc);
    setOrders(ord?.items ?? []);
  };

  useEffect(() => {
    void load();
  }, []);

  const submit = async () => {
    const res = await apiPost<{ status: string; reason?: unknown; price?: number; fee_total?: number }>('/api/paper/orders', {
      code,
      side,
      qty,
      order_type: 'MARKET'
    });
    setMessage(
      res?.status === 'FILLED'
        ? `${t('paper.filled')} ${res.price} × ${qty} (${t('paper.fee')} ${res.fee_total})`
        : `${t('paper.rejected')}: ${JSON.stringify(res?.reason ?? '')}`
    );
    await load();
  };

  const reset = async () => {
    await apiPost('/api/paper/reset');
    setMessage(t('paper.resetDone'));
    await load();
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{t('paper.title')}</h1>
          <p className="subtitle">{t('paper.subtitle')}</p>
        </div>
        <button className="chip" onClick={() => void reset()}>{t('paper.reset')}</button>
      </header>

      <div className="metric-grid">
        <div className="metric"><span>{t('paper.totalAsset')}</span><b>{account?.total_asset?.toLocaleString() ?? '—'}</b></div>
        <div className="metric"><span>{t('paper.cash')}</span><b>{account?.account.cash.toLocaleString() ?? '—'}</b></div>
        <div className="metric"><span>{t('paper.marketValue')}</span><b>{account?.market_value?.toLocaleString() ?? '—'}</b></div>
        <div className="metric"><span>{t('paper.pnl')}</span><b>{account?.pnl?.toLocaleString() ?? '—'}</b></div>
      </div>

      <div className="panel">
        <h2>{t('paper.order')}</h2>
        <div className="row">
          <input className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="code" />
          <select className="input" value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="BUY">{t('paper.buy')}</option>
            <option value="SELL">{t('paper.sell')}</option>
          </select>
          <input className="input" type="number" value={qty} onChange={(e) => setQty(Number(e.target.value))} />
          <button className="chip primary" onClick={() => void submit()}>{t('paper.submit')}</button>
        </div>
        {message && <p className="meta">{message}</p>}
      </div>

      <div className="panel">
        <h2>{t('paper.positions')}</h2>
        <table className="table">
          <thead>
            <tr>
              <th>{t('paper.code')}</th><th>{t('paper.name')}</th><th>{t('paper.qty')}</th>
              <th>{t('paper.sellable')}</th><th>{t('paper.avgCost')}</th><th>{t('paper.last')}</th><th>{t('paper.pnl')}</th>
            </tr>
          </thead>
          <tbody>
            {(account?.positions ?? []).map((p) => (
              <tr key={p.code}>
                <td>{p.code}</td><td>{p.name ?? '—'}</td><td>{p.qty}</td>
                <td>{p.sellable_qty}</td><td>{p.avg_cost}</td><td>{p.last ?? '—'}</td><td>{p.pnl}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(account?.positions ?? []).length === 0 && <p className="meta">{t('paper.noPositions')}</p>}
      </div>

      <div className="panel">
        <h2>{t('paper.orders')}</h2>
        <table className="table">
          <thead>
            <tr><th>#</th><th>{t('paper.code')}</th><th>{t('paper.side')}</th><th>{t('paper.qty')}</th><th>{t('paper.status')}</th><th>{t('paper.time')}</th></tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{o.id}</td><td>{o.code}</td><td>{o.side}</td><td>{o.qty}</td>
                <td>{o.status}{o.reject_reason ? ` (${o.reject_reason})` : ''}</td><td>{o.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

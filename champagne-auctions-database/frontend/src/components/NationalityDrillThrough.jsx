import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { X, ExternalLink, ArrowUpDown } from 'lucide-react';

// Drill-through dei grafici nazionalità: mostra i lotti (chiusi e venduti)
// attribuiti a una nazionalità, con gli stessi criteri usati dai grafici.
//
// props:
//   drill:   { country, filters: { maison|distilleria, tipologia|stile }, context } oppure null
//   onClose: chiude il pannello
//   fields:  nomi dei campi del progetto, es.
//            { group: 'maison', groupLabel: 'Maison', type: 'tipologia', typeLabel: 'Tipologia',
//              age: 'vintage', ageLabel: 'Annata' }

const accent = 'var(--accent-gold, var(--accent-color, #c5a059))';

const countryName = (code) => {
  try {
    return new Intl.DisplayNames(['it'], { type: 'region' }).of(code) || code;
  } catch {
    return code;
  }
};

const flag = (code) =>
  /^[A-Z]{2}$/.test(code || '')
    ? String.fromCodePoint(...[...code].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65))
    : '';

const euro = (v) =>
  v == null ? '–' : `€ ${Number(v).toLocaleString('it-IT', { maximumFractionDigits: 2 })}`;

const NationalityDrillThrough = ({ drill, onClose, fields }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sort, setSort] = useState({ key: 'data_chiusura', dir: 'desc' });

  useEffect(() => {
    if (!drill) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    const params = { country: drill.country };
    Object.entries(drill.filters || {}).forEach(([k, v]) => {
      if (v) params[k] = v;
    });
    axios
      .get('/api/analysis/nationality-lots', { params })
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch((e) => { if (!cancelled) setError(e?.message || 'Errore di caricamento'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [drill]);

  useEffect(() => {
    if (!drill) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drill, onClose]);

  const columns = [
    { key: 'data_chiusura', label: 'Chiusura' },
    { key: 'title', label: 'Lotto' },
    { key: fields.type, label: fields.typeLabel },
    { key: fields.age, label: fields.ageLabel },
    { key: 'formato', label: 'Formato' },
    { key: 'numero_bottiglie', label: 'Bott.', numeric: true },
    { key: 'numero_offerte', label: 'Offerte', numeric: true },
    { key: 'prezzo_finale', label: 'Prezzo finale', numeric: true },
  ];

  const rows = useMemo(() => {
    const list = [...(data?.lots || [])];
    const { key, dir } = sort;
    list.sort((a, b) => {
      const x = a[key], y = b[key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'it');
      return dir === 'asc' ? c : -c;
    });
    return list;
  }, [data, sort]);

  if (!drill) return null;

  const toggleSort = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'desc' ? 'asc' : 'desc' }));

  const th = { padding: '10px 12px', textAlign: 'left', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap', position: 'sticky', top: 0, background: '#141414' };
  const td = { padding: '9px 12px', fontSize: '0.85rem', borderTop: '1px solid rgba(255,255,255,0.06)', verticalAlign: 'top' };

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.72)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}
    >
      <div
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        style={{ background: '#101010', border: '1px solid var(--glass-border)', borderRadius: '16px', width: 'min(1100px, 100%)', maxHeight: '88vh', display: 'flex', flexDirection: 'column', boxShadow: '0 24px 48px rgba(0,0,0,0.6)' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--glass-border)' }}>
          <div>
            <h3 className="font-outfit" style={{ margin: 0, fontSize: '1.3rem' }}>
              {flag(drill.country)} {countryName(drill.country)}
              <span style={{ color: 'var(--text-secondary)', fontWeight: 400, fontSize: '0.95rem' }}> · lotti vinti</span>
            </h3>
            {drill.context && (
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '4px' }}>{drill.context}</p>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Chiudi"
            style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-primary)', borderRadius: '8px', padding: '6px', cursor: 'pointer', display: 'flex' }}
          >
            <X size={18} />
          </button>
        </div>

        {data && (
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', padding: '1rem 1.5rem' }}>
            {[
              ['Lotti', data.total_lots.toLocaleString('it-IT')],
              ['Spesa totale', euro(data.total_spent)],
              ['Prezzo medio', euro(data.avg_price)],
            ].map(([label, value]) => (
              <div key={label}>
                <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 700, color: accent }}>{value}</div>
              </div>
            ))}
          </div>
        )}

        <div style={{ overflow: 'auto', padding: '0 0.5rem 1rem' }}>
          {loading && <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Caricamento lotti…</div>}
          {error && <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--danger)' }}>{error}</div>}
          {data && rows.length === 0 && (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Nessun lotto per questa selezione.</div>
          )}
          {data && rows.length > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th key={c.key} style={{ ...th, textAlign: c.numeric ? 'right' : 'left' }} onClick={() => toggleSort(c.key)}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                        {c.label}
                        <ArrowUpDown size={11} style={{ opacity: sort.key === c.key ? 1 : 0.35 }} />
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.id}>
                    <td style={{ ...td, whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{l.data_chiusura || '–'}</td>
                    <td style={{ ...td, minWidth: '260px' }}>
                      <a href={l.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
                        {l.title} <ExternalLink size={11} style={{ opacity: 0.5, verticalAlign: 'middle' }} />
                      </a>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        {l[fields.group]}{l.winner_username && l.winner_username !== 'Unknown' ? ` · ${l.winner_username}` : ''}
                      </div>
                    </td>
                    <td style={td}>{l[fields.type] || '–'}</td>
                    <td style={td}>{l[fields.age] || '–'}</td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>{l.formato || '–'}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{l.numero_bottiglie ?? '–'}</td>
                    <td style={{ ...td, textAlign: 'right' }}>{l.numero_offerte ?? '–'}</td>
                    <td style={{ ...td, textAlign: 'right', fontWeight: 600, whiteSpace: 'nowrap' }}>{euro(l.prezzo_finale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data && data.total_lots > rows.length && (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', padding: '0.75rem' }}>
              Mostrati i {rows.length} lotti più recenti su {data.total_lots}.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default NationalityDrillThrough;

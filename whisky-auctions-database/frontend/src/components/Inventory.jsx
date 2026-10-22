import React, { useState, useMemo } from 'react';
import { Search, ExternalLink, Filter, ChevronRight, ChevronDown, Wine, Package, X, Info } from 'lucide-react';

// Distillerie/etichette che in realtà sono imbottigliatori indipendenti con
// distilleria d'origine non dichiarata. L'alert spiega la cosa all'utente
// invece di lasciar credere che sia un nome di distilleria vero.
const ORIGINAL_BOTTLING = 'Original bottling';

const UNDISCLOSED_SOURCE_LABELS = {
  'SexyWhisky': {
    it: 'SexyWhisky non è una distilleria: è un imbottigliatore indipendente che vende whisky di provenienza non dichiarata (pratica comune quando la distilleria d\'origine non permette di stampare il proprio nome in etichetta). Il nome che vedi nel titolo del lotto (es. "1960 Highland Distillery") è lo pseudonimo scelto da SexyWhisky per quella specifica serie/botte, non il nome reale del produttore.',
    en: 'SexyWhisky is not a distillery: it\'s an independent bottler that sells whisky from undisclosed sources (common when the source distillery does not allow its name to appear on the label). The name shown in the lot title (e.g. "1960 Highland Distillery") is the pseudonym SexyWhisky chose for that specific series/cask, not the real producer\'s name.',
  },
};

const InventoryView = ({ lots, loading, onSelectLot }) => {
  const [search, setSearch] = useState('');
  const [expandedDistillerias, setExpandedDistillerias] = useState(new Set());
  const [expandedStili, setExpandedStili] = useState(new Set());
  const [boxFilter, setBoxFilter] = useState('all');
  // Filtro imbottigliatore: 'all', '__independent__', '__original__' oppure un nome
  const [bottlerFilter, setBottlerFilter] = useState('all');
  const [sourceInfoModal, setSourceInfoModal] = useState(null);

  const bottlerOf = (lot) => lot.imbottigliatore || ORIGINAL_BOTTLING;
  const matchesBottler = (lot) => {
    if (bottlerFilter === 'all') return true;
    const b = bottlerOf(lot);
    if (bottlerFilter === '__independent__') return b !== ORIGINAL_BOTTLING;
    if (bottlerFilter === '__original__') return b === ORIGINAL_BOTTLING;
    return b === bottlerFilter;
  };

  // Voci del menu "Bottlers": imbottigliatori indipendenti con numero di lotti
  const bottlerOptions = useMemo(() => {
    const counts = {};
    (lots || []).forEach(lot => {
      const b = bottlerOf(lot);
      counts[b] = (counts[b] || 0) + 1;
    });
    const independent = Object.entries(counts)
      .filter(([name]) => name !== ORIGINAL_BOTTLING)
      // ordine alfabetico (maiuscole/accenti ignorati)
      .sort((a, b) => a[0].localeCompare(b[0], 'en', { sensitivity: 'base' }));
    const totalIndependent = independent.reduce((s, [, n]) => s + n, 0);
    return { independent, totalIndependent, original: counts[ORIGINAL_BOTTLING] || 0 };
  }, [lots]);

  const hierarchicalData = useMemo(() => {
    if (!lots) return {};
    
    const filtered = lots.filter(lot => 
      ((lot.distilleria || '').toLowerCase().includes(search.toLowerCase()) ||
       (lot.title || '').toLowerCase().includes(search.toLowerCase())) &&
      (boxFilter === 'all' || (boxFilter === 'yes' ? lot.has_box : !lot.has_box)) &&
      matchesBottler(lot)
    );

    const grouped = {};
    filtered.forEach(lot => {
      const distilleria = lot.distilleria || 'Unknown';
      const stile = lot.stile || 'Unknown';
      const eta = lot.eta || 'NV';
      
      if (!grouped[distilleria]) {
        grouped[distilleria] = {};
      }
      if (!grouped[distilleria][stile]) {
        grouped[distilleria][stile] = {};
      }
      if (!grouped[distilleria][stile][eta]) {
        grouped[distilleria][stile][eta] = [];
      }
      grouped[distilleria][stile][eta].push(lot);
    });

    // Sort everything alphabetically
    const sortedGrouped = {};
    Object.keys(grouped).sort().forEach(distilleria => {
      sortedGrouped[distilleria] = {};
      Object.keys(grouped[distilleria]).sort().forEach(stile => {
        sortedGrouped[distilleria][stile] = {};
        Object.keys(grouped[distilleria][stile]).sort().forEach(eta => {
          sortedGrouped[distilleria][stile][eta] = grouped[distilleria][stile][eta];
        });
      });
    });

    return sortedGrouped;
  }, [lots, search, boxFilter, bottlerFilter]);

  const toggleDistilleria = (distilleria) => {
    const newExpanded = new Set(expandedDistillerias);
    const isOpening = !newExpanded.has(distilleria);
    if (newExpanded.has(distilleria)) {
      newExpanded.delete(distilleria);
    } else {
      newExpanded.add(distilleria);
    }
    setExpandedDistillerias(newExpanded);

    if (isOpening && UNDISCLOSED_SOURCE_LABELS[distilleria]) {
      setSourceInfoModal(distilleria);
    }
  };

  const toggleStile = (distilleria, stile) => {
    const key = `${distilleria}-${stile}`;
    const newExpanded = new Set(expandedStili);
    if (newExpanded.has(key)) {
      newExpanded.delete(key);
    } else {
      newExpanded.add(key);
    }
    setExpandedStili(newExpanded);
  };

  const getDistilleriaStats = (distilleriaData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    Object.values(distilleriaData).forEach(stileData => {
      Object.values(stileData).forEach(etaData => {
        etaData.forEach(lot => {
          totalLots++;
          if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
          if (lot.status === 'OPEN') activeLots++;
        });
      });
    });
    
    return { totalLots, totalValue, activeLots };
  };

  const getStileStats = (stileData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    Object.values(stileData).forEach(etaData => {
      etaData.forEach(lot => {
        totalLots++;
        if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
        if (lot.status === 'OPEN') activeLots++;
      });
    });
    
    return { totalLots, totalValue, activeLots };
  };

  const getEtaStats = (etaData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    etaData.forEach(lot => {
      totalLots++;
      if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
      if (lot.status === 'OPEN') activeLots++;
    });
    
    return { totalLots, totalValue, activeLots };
  };

  return (
    <div className="inventory-view">
      {sourceInfoModal && UNDISCLOSED_SOURCE_LABELS[sourceInfoModal] && (
        <div
          onClick={() => setSourceInfoModal(null)}
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="glass-card"
            style={{
              maxWidth: '520px',
              width: '90%',
              padding: '1.5rem',
              background: '#141414',
              border: '1px solid var(--glass-border)',
              borderRadius: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <Info size={20} style={{ color: 'var(--accent-color)' }} />
                <span style={{ fontWeight: '700', fontSize: '1.1rem' }}>{sourceInfoModal}</span>
              </div>
              <button
                onClick={() => setSourceInfoModal(null)}
                style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', padding: '4px' }}
              >
                <X size={20} />
              </button>
            </div>
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '4px' }}>Italiano</div>
              <p style={{ fontSize: '0.9rem', lineHeight: '1.5', margin: 0 }}>{UNDISCLOSED_SOURCE_LABELS[sourceInfoModal].it}</p>
            </div>
            <div>
              <div style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)', marginBottom: '4px' }}>English</div>
              <p style={{ fontSize: '0.9rem', lineHeight: '1.5', margin: 0, color: 'var(--text-secondary)' }}>{UNDISCLOSED_SOURCE_LABELS[sourceInfoModal].en}</p>
            </div>
          </div>
        </div>
      )}
      <div className="glass-card" style={{ padding: '0' }}>
        <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: '300px' }}>
            <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
            <input 
              type="text" 
              placeholder="Search distillery or title..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                padding: '10px 10px 10px 40px',
                color: 'white',
                outline: 'none'
              }}
            />
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <select 
              value={boxFilter} 
              onChange={(e) => setBoxFilter(e.target.value)}
              style={{
                backgroundColor: 'rgba(255,255,255,0.05)',
                color: 'white',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                padding: '0 12px',
                fontSize: '14px',
                cursor: 'pointer'
              }}
            >
              <option value="all" style={{ backgroundColor: 'black' }}>Box: All</option>
              <option value="yes" style={{ backgroundColor: 'black' }}>Box: Yes</option>
              <option value="no" style={{ backgroundColor: 'black' }}>Box: No</option>
            </select>
            <select
              value={bottlerFilter}
              onChange={(e) => setBottlerFilter(e.target.value)}
              title="Bottlers: imbottigliatori indipendenti"
              style={{
                backgroundColor: 'rgba(255,255,255,0.05)',
                color: 'white',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                padding: '0 12px',
                fontSize: '14px',
                cursor: 'pointer',
                maxWidth: '260px'
              }}
            >
              <option value="all" style={{ backgroundColor: 'black' }}>Bottlers: All</option>
              <option value="__original__" style={{ backgroundColor: 'black' }}>Original bottling ({bottlerOptions.original})</option>
              <option value="__independent__" style={{ backgroundColor: 'black' }}>All independent bottlers ({bottlerOptions.totalIndependent})</option>
              {bottlerOptions.independent.map(([name, n]) => (
                <option key={name} value={name} style={{ backgroundColor: 'black' }}>{name} ({n})</option>
              ))}
            </select>
            <button style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'white', padding: '8px 16px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
              <Filter size={18} />
              Filters
            </button>
          </div>
        </div>

        <div style={{ overflowY: 'auto', maxHeight: 'calc(100vh - 300px)' }}>
          {loading ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Loading lots...</div>
          ) : Object.keys(hierarchicalData).length === 0 ? (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>Nessun lotto trovato</div>
          ) : (
            <div style={{ padding: '1rem' }}>
              {Object.entries(hierarchicalData).map(([distilleria, distilleryData]) => {
                const distilleryStats = getDistilleriaStats(distilleryData);
                const isExpanded = expandedDistillerias.has(distilleria);
                
                return (
                  <div key={distilleria} style={{ marginBottom: '0.5rem' }}>
                    {/* Distillery Level */}
                    <div 
                      onClick={() => toggleDistilleria(distilleria)}
                      style={{ 
                        display: 'flex', 
                        alignItems: 'center', 
                        padding: '12px 16px',
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid var(--glass-border)',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        marginBottom: '4px'
                      }}
                      className="hover-row"
                    >
                      {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                      <Wine size={18} style={{ marginLeft: '8px', marginRight: '12px', color: 'var(--accent-color)' }} />
                      <div style={{ flex: 1 }}>
                        <span style={{ fontWeight: '600', fontSize: '1.1rem' }}>{distilleria}</span>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {distilleryStats.totalLots} lots • €{distilleryStats.totalValue.toLocaleString()} total • {distilleryStats.activeLots} active
                        </div>
                      </div>
                    </div>

                    {/* Stile Level */}
                    {isExpanded && Object.entries(distilleryData).map(([stile, stileData]) => {
                      const stileStats = getStileStats(stileData);
                      const stileKey = `${distilleria}-${stile}`;
                      const isStileExpanded = expandedStili.has(stileKey);
                      
                      return (
                        <div key={stile} style={{ marginLeft: '24px', marginBottom: '0.25rem' }}>
                          <div 
                            onClick={() => toggleStile(distilleria, stile)}
                            style={{ 
                              display: 'flex', 
                              alignItems: 'center', 
                              padding: '8px 12px',
                              background: 'rgba(255,255,255,0.01)',
                              border: '1px solid rgba(255,255,255,0.1)',
                              borderRadius: '6px',
                              cursor: 'pointer',
                              marginBottom: '2px'
                            }}
                            className="hover-row"
                          >
                            {isStileExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            <span style={{ marginLeft: '8px', fontWeight: '500', fontSize: '0.95rem' }}>{stile}</span>
                            <div style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {stileStats.totalLots} lots • €{stileStats.totalValue.toLocaleString()}
                            </div>
                          </div>

                          {/* Eta Level */}
                          {isStileExpanded && Object.entries(stileData).map(([eta, etaData]) => {
                            const etaStats = getEtaStats(etaData);
                            
                            return (
                              <div key={eta} style={{ marginLeft: '24px', marginBottom: '0.25rem' }}>
                                <div style={{ 
                                  display: 'flex', 
                                  alignItems: 'center', 
                                  padding: '6px 10px',
                                  background: 'rgba(255,255,255,0.005)',
                                  border: '1px solid rgba(255,255,255,0.05)',
                                  borderRadius: '4px',
                                  marginBottom: '1px'
                                }}>
                                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{eta}</span>
                                  <div style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                                    {etaStats.totalLots} lots • €{etaStats.totalValue.toLocaleString()}
                                  </div>
                                </div>

                                {/* Individual Lots */}
                                {etaData.map((lot, idx) => (
                                  <div 
                                    key={idx} 
                                    onClick={() => onSelectLot(lot)}
                                    style={{ 
                                      display: 'flex', 
                                      alignItems: 'center',
                                      padding: '4px 8px',
                                      marginLeft: '12px',
                                      cursor: 'pointer',
                                      borderRadius: '3px'
                                    }}
                                    className="hover-row"
                                  >
                                    <div style={{ flex: 1, fontSize: '0.8rem' }}>
                                      <span style={{ color: 'var(--text-secondary)' }}>
                                        {lot.numero_bottiglie} btl • {lot.numero_offerte} bids
                                      </span>
                                      {lot.prezzo_finale && (
                                        <span style={{ marginLeft: '8px', fontWeight: '600', color: 'var(--accent-color)' }}>
                                          €{lot.prezzo_finale.toLocaleString()}
                                        </span>
                                      )}
                                      {lot.imbottigliatore && lot.imbottigliatore !== ORIGINAL_BOTTLING && (
                                        <span title="Imbottigliatore indipendente" style={{
                                          marginLeft: '8px',
                                          fontSize: '0.65rem',
                                          padding: '1px 5px',
                                          background: 'rgba(255,255,255,0.06)',
                                          color: 'var(--text-secondary)',
                                          border: '1px solid rgba(255,255,255,0.12)',
                                          borderRadius: '3px',
                                          verticalAlign: 'middle'
                                        }}>
                                          {lot.imbottigliatore}
                                        </span>
                                      )}
                                      {lot.has_box && (
                                        <span style={{ 
                                          marginLeft: '8px', 
                                          fontSize: '0.65rem', 
                                          padding: '1px 4px', 
                                          background: 'rgba(197, 160, 89, 0.2)', 
                                          color: '#c5a059', 
                                          border: '1px solid rgba(197, 160, 89, 0.3)',
                                          borderRadius: '3px',
                                          verticalAlign: 'middle',
                                          display: 'inline-flex',
                                          alignItems: 'center',
                                          gap: '2px'
                                        }}>
                                          <Package size={10} /> BOX
                                        </span>
                                      )}
                                    </div>
                                    <span className={`status-badge ${lot.status === 'OPEN' ? 'status-open' : 'status-closed'}`} style={{ fontSize: '0.7rem', padding: '2px 6px' }}>
                                      {lot.status}
                                    </span>
                                    <a 
                                      href={lot.url} 
                                      target="_blank" 
                                      rel="noopener noreferrer" 
                                      style={{ marginLeft: '8px', color: 'var(--text-secondary)' }}
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <ExternalLink size={12} />
                                    </a>
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default InventoryView;

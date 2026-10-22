import React, { useState, useMemo } from 'react';
import { Search, ExternalLink, Filter, ChevronRight, ChevronDown, Wine, Package } from 'lucide-react';

const InventoryView = ({ lots, loading, onSelectLot }) => {
  const [search, setSearch] = useState('');
  const [expandedMaisons, setExpandedMaisons] = useState(new Set());
  const [expandedTipologias, setExpandedTipologias] = useState(new Set());
  const [boxFilter, setBoxFilter] = useState('all');

  const hierarchicalData = useMemo(() => {
    if (!lots) return {};
    
    const filtered = lots.filter(lot => {
      const matchesSearch = (lot.maison || '').toLowerCase().includes(search.toLowerCase()) ||
                            (lot.title || '').toLowerCase().includes(search.toLowerCase());
      const matchesBox = boxFilter === 'all' || 
                         (boxFilter === 'yes' && lot.has_box) || 
                         (boxFilter === 'no' && !lot.has_box);
      return matchesSearch && matchesBox;
    });

    const grouped = {};
    filtered.forEach(lot => {
      const maison = lot.maison || 'Unknown';
      const tipologia = lot.tipologia || 'Unknown';
      const vintage = lot.vintage || 'NV';
      
      if (!grouped[maison]) {
        grouped[maison] = {};
      }
      if (!grouped[maison][tipologia]) {
        grouped[maison][tipologia] = {};
      }
      if (!grouped[maison][tipologia][vintage]) {
        grouped[maison][tipologia][vintage] = [];
      }
      grouped[maison][tipologia][vintage].push(lot);
    });

    // Sort everything alphabetically
    const sortedGrouped = {};
    Object.keys(grouped).sort().forEach(maison => {
      sortedGrouped[maison] = {};
      Object.keys(grouped[maison]).sort().forEach(tipologia => {
        sortedGrouped[maison][tipologia] = {};
        Object.keys(grouped[maison][tipologia]).sort().forEach(vintage => {
          sortedGrouped[maison][tipologia][vintage] = grouped[maison][tipologia][vintage];
        });
      });
    });

    return sortedGrouped;
  }, [lots, search]);

  const toggleMaison = (maison) => {
    const newExpanded = new Set(expandedMaisons);
    if (newExpanded.has(maison)) {
      newExpanded.delete(maison);
    } else {
      newExpanded.add(maison);
    }
    setExpandedMaisons(newExpanded);
  };

  const toggleTipologia = (maison, tipologia) => {
    const key = `${maison}-${tipologia}`;
    const newExpanded = new Set(expandedTipologias);
    if (newExpanded.has(key)) {
      newExpanded.delete(key);
    } else {
      newExpanded.add(key);
    }
    setExpandedTipologias(newExpanded);
  };

  const getMaisonStats = (maisonData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    Object.values(maisonData).forEach(tipologiaData => {
      Object.values(tipologiaData).forEach(vintageData => {
        vintageData.forEach(lot => {
          totalLots++;
          if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
          if (lot.status === 'OPEN') activeLots++;
        });
      });
    });
    
    return { totalLots, totalValue, activeLots };
  };

  const getTipologiaStats = (tipologiaData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    Object.values(tipologiaData).forEach(vintageData => {
      vintageData.forEach(lot => {
        totalLots++;
        if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
        if (lot.status === 'OPEN') activeLots++;
      });
    });
    
    return { totalLots, totalValue, activeLots };
  };

  const getVintageStats = (vintageData) => {
    let totalLots = 0;
    let totalValue = 0;
    let activeLots = 0;
    
    vintageData.forEach(lot => {
      totalLots++;
      if (lot.prezzo_finale) totalValue += lot.prezzo_finale;
      if (lot.status === 'OPEN') activeLots++;
    });
    
    return { totalLots, totalValue, activeLots };
  };

  return (
    <div className="inventory-view">
      <div className="glass-card" style={{ padding: '0' }}>
        <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: '300px' }}>
            <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
            <input 
              type="text" 
              placeholder="Search maison or title..." 
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
          <div style={{ display: 'flex', gap: '10px' }}>
            <select 
              value={boxFilter} 
              onChange={(e) => setBoxFilter(e.target.value)}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: '8px',
                padding: '8px 12px',
                color: 'white',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="all">All Boxes</option>
              <option value="yes">With Box</option>
              <option value="no">Without Box</option>
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
              {Object.entries(hierarchicalData).map(([maison, maisonData]) => {
                const maisonStats = getMaisonStats(maisonData);
                const isExpanded = expandedMaisons.has(maison);
                
                return (
                  <div key={maison} style={{ marginBottom: '0.5rem' }}>
                    {/* Maison Level */}
                    <div 
                      onClick={() => toggleMaison(maison)}
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
                      <Wine size={18} style={{ marginLeft: '8px', marginRight: '12px', color: 'var(--accent-gold)' }} />
                      <div style={{ flex: 1 }}>
                        <span style={{ fontWeight: '600', fontSize: '1.1rem' }}>{maison}</span>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                          {maisonStats.totalLots} lots • €{maisonStats.totalValue.toLocaleString()} total • {maisonStats.activeLots} active
                        </div>
                      </div>
                    </div>

                    {/* Tipologia Level */}
                    {isExpanded && Object.entries(maisonData).map(([tipologia, tipologiaData]) => {
                      const tipologiaStats = getTipologiaStats(tipologiaData);
                      const tipologiaKey = `${maison}-${tipologia}`;
                      const isTipologiaExpanded = expandedTipologias.has(tipologiaKey);
                      
                      return (
                        <div key={tipologia} style={{ marginLeft: '24px', marginBottom: '0.25rem' }}>
                          <div 
                            onClick={() => toggleTipologia(maison, tipologia)}
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
                            {isTipologiaExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            <span style={{ marginLeft: '8px', fontWeight: '500', fontSize: '0.95rem' }}>{tipologia}</span>
                            <div style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                              {tipologiaStats.totalLots} lots • €{tipologiaStats.totalValue.toLocaleString()}
                            </div>
                          </div>

                          {/* Vintage Level */}
                          {isTipologiaExpanded && Object.entries(tipologiaData).map(([vintage, vintageData]) => {
                            const vintageStats = getVintageStats(vintageData);
                            
                            return (
                              <div key={vintage} style={{ marginLeft: '24px', marginBottom: '0.25rem' }}>
                                <div style={{ 
                                  display: 'flex', 
                                  alignItems: 'center', 
                                  padding: '6px 10px',
                                  background: 'rgba(255,255,255,0.005)',
                                  border: '1px solid rgba(255,255,255,0.05)',
                                  borderRadius: '4px',
                                  marginBottom: '1px'
                                }}>
                                  <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{vintage}</span>
                                  <div style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-secondary)' }}>
                                    {vintageStats.totalLots} lots • €{vintageStats.totalValue.toLocaleString()}
                                  </div>
                                </div>

                                {/* Individual Lots */}
                                {vintageData.map((lot, idx) => (
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
                                        <span style={{ marginLeft: '8px', fontWeight: '600', color: 'var(--accent-gold)' }}>
                                          €{lot.prezzo_finale.toLocaleString()}
                                        </span>
                                      )}
                                      {lot.has_box && (
                                        <span style={{ 
                                          marginLeft: '12px', 
                                          display: 'inline-flex', 
                                          alignItems: 'center', 
                                          gap: '4px',
                                          background: 'rgba(197, 160, 89, 0.15)',
                                          color: '#c5a059',
                                          padding: '1px 6px',
                                          borderRadius: '4px',
                                          fontSize: '0.65rem',
                                          fontWeight: '700',
                                          border: '1px solid rgba(197, 160, 89, 0.3)'
                                        }}>
                                          <Package size={10} />
                                          BOX
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

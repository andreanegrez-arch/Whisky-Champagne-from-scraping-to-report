import React, { useState, useEffect, useCallback, useRef } from 'react';
import ReactECharts from 'echarts-for-react';
import { BarChart, PieChart, MapPin, Package, TrendingUp, Info } from 'lucide-react';
import axios from 'axios';
import NationalityDrillThrough from './NationalityDrillThrough';

// Valori che non sono una nazionalità: esclusi dai grafici.
const UNKNOWN_NATS = ['Unknown', 'Sconosciuto', 'NV', ''];
const isKnownNat = (n) => !!n && !UNKNOWN_NATS.includes(n);

const AnalysisView = ({ stats, loading }) => {
  const [nationalityData, setNationalityData] = useState({});
  const [selectedMaison, setSelectedMaison] = useState('');
  const [natLoading, setNatLoading] = useState(false);
  
  const [topNatData, setTopNatData] = useState([]);
  const [topNatLoading, setTopNatLoading] = useState(false);

  // Drill-through: nazionalità cliccata nei grafici -> elenco dei lotti
  const [drill, setDrill] = useState(null);
  const closeDrill = useCallback(() => setDrill(null), []);

  // Load nationality data on mount
  useEffect(() => {
    const loadNationalities = async () => {
      try {
        setNatLoading(true);
        const response = await axios.get('/api/analysis/nationalities');
        setNationalityData(response.data || {});
      } catch (err) {
        console.error('Error loading nationalities:', err);
      } finally {
        setNatLoading(false);
      }
    };
    const loadTopNationalities = async () => {
      try {
        setTopNatLoading(true);
        const response = await axios.get('/api/analysis/top-nationalities');
        setTopNatData(response.data || []);
      } catch (err) {
        console.error('Error loading top nationalities:', err);
      } finally {
        setTopNatLoading(false);
      }
    };

    loadNationalities();
    loadTopNationalities();
  }, []);

  const [deepHierarchy, setDeepHierarchy] = useState([]);
  const [deepMaison, setDeepMaison] = useState('');
  const [deepTipologia, setDeepTipologia] = useState('');
  const [deepVintage, setDeepVintage] = useState('');
  const [deepFormato, setDeepFormato] = useState('');
  const [deepHasBox, setDeepHasBox] = useState('all');
  const [deepFilterMode, setDeepFilterMode] = useState('all');
  const [deepBottleData, setDeepBottleData] = useState(null);
  const [deepLoading, setDeepLoading] = useState(false);
  // Contatore per scartare le risposte "in ritardo": se l'utente cambia annata
  // (o maison/tipologia/formato) rapidamente, una richiesta precedente più lenta
  // potrebbe rispondere DOPO quella più recente e sovrascrivere il grafico con
  // i dati sbagliati (stessa annata mostrata sempre uguale). Questo id fa sì
  // che solo la risposta della richiesta più recente venga applicata.
  const deepRequestIdRef = useRef(0);

  useEffect(() => {
    const loadDeepHierarchy = async () => {
      try {
        const response = await axios.get('/api/analysis/hierarchy');
        setDeepHierarchy(response.data || []);
      } catch (err) {}
    };
    loadDeepHierarchy();
  }, []);

  useEffect(() => {
    if (deepMaison && deepTipologia && deepVintage && deepFormato) {
      const requestId = ++deepRequestIdRef.current;
      const loadDeepBottle = async () => {
        try {
          setDeepLoading(true);
          const params = {
            maison: deepMaison,
            tipologia: deepTipologia,
            vintage: deepVintage,
            formato: deepFormato,
            filter_mode: deepFilterMode
          };
          if (deepHasBox !== 'all') {
            params.has_box = deepHasBox === 'yes';
          }
          const response = await axios.get('/api/analysis/bottle', { params });
          if (requestId === deepRequestIdRef.current) {
            setDeepBottleData(response.data);
          }
        } catch (err) {} finally {
          if (requestId === deepRequestIdRef.current) {
            setDeepLoading(false);
          }
        }
      };
      loadDeepBottle();
    } else {
      deepRequestIdRef.current++;
      setDeepBottleData(null);
    }
  }, [deepMaison, deepTipologia, deepVintage, deepFormato, deepHasBox, deepFilterMode]);

  if (loading || !stats) return <div style={{ color: 'var(--text-secondary)' }}>Loading analysis...</div>;

  const topMaisonData = stats.maison_stats.slice(0, 15);

  const priceOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { textStyle: { color: 'var(--text-secondary)' }, bottom: 0 },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: {
      type: 'value',
      boundaryGap: [0, 0.01],
      axisLabel: { color: 'var(--text-secondary)' },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
    },
    yAxis: {
      type: 'category',
      data: topMaisonData.map(s => s.maison),
      axisLabel: { color: 'var(--text-secondary)' }
    },
    series: [
      {
        name: 'Avg Price',
        type: 'bar',
        data: topMaisonData.map(s => s.prezzo_medio),
        itemStyle: { color: '#c5a059' }
      },
      {
        name: 'Max Price',
        type: 'bar',
        data: topMaisonData.map(s => s.prezzo_max),
        itemStyle: { color: '#3498db' }
      }
    ]
  };

  // Prepare nationality chart data
  const getNationalityChartData = (maison) => {
    if (!nationalityData[maison]) return [];
    
    return nationalityData[maison]
      .filter(n => isKnownNat(n.nationality))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10); // Top 10 nationalities
  };

  // Click su una fetta della torta -> lotti vinti da quella nazionalità per la maison selezionata
  const currentNatGroup = selectedMaison || Object.keys(nationalityData)[0] || '';
  const nationalityEvents = {
    click: (p) => {
      if (!p?.name || !isKnownNat(p.name)) return;
      setDrill({ country: p.name, filters: { maison: currentNatGroup }, context: `Maison: ${currentNatGroup}` });
    }
  };

  // Click su un segmento delle barre -> lotti di quella nazionalità per quella bottiglia
  const topNatEvents = {
    click: (p) => {
      const b = topNatData[p?.dataIndex];
      if (!b || !isKnownNat(p.seriesName)) return;
      setDrill({ country: p.seriesName, filters: { maison: b.maison, tipologia: b.tipologia }, context: `${b.maison} – ${b.tipologia}` });
    }
  };

  const nationalityOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { 
      textStyle: { color: 'var(--text-secondary)' }, 
      bottom: 0,
      type: 'scroll'
    },
    series: [{
      name: 'Nationalities',
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      data: getNationalityChartData(selectedMaison || Object.keys(nationalityData)[0] || '').map(item => ({
        value: item.count,
        name: item.nationality || 'Unknown'
      })),
      emphasis: {
        itemStyle: {
          shadowBlur: 10,
          shadowOffsetX: 0,
          shadowColor: 'rgba(0, 0, 0, 0.5)'
        }
      },
      label: {
        color: 'var(--text-secondary)',
        formatter: '{b}: {d}%'
      }
    }]
  };

  // Prepare Top Nationalities Stacked Bar Chart data
  const uniqueCountries = [...new Set(topNatData.flatMap(b => b.nationalities.map(n => n.country)))].filter(isKnownNat);
  
  const seriesData = uniqueCountries.map(country => {
    return {
      name: country,
      type: 'bar',
      stack: 'total',
      label: { show: true, position: 'inside', formatter: (p) => p.value > 0 ? p.value : '', color: '#fff', fontSize: 10 },
      emphasis: { focus: 'series' },
      data: topNatData.map(bottle => {
        const nat = bottle.nationalities.find(n => n.country === country);
        return {
          value: nat ? nat.lots_won : 0,
          avg_price: nat ? nat.avg_price : 0
        };
      })
    };
  });

  const topNatOption = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: function(params) {
        let res = `<div style="padding:4px"><b style="font-size:13px">${params[0].axisValue}</b><br/>`;
        params.forEach(p => {
          if (p.value > 0) {
            res += `<div style="display:flex; justify-content:space-between; width:220px; font-size:12px; margin-top:4px">
                      <span>${p.marker} ${p.seriesName}</span>
                      <span style="font-weight:700">${p.value} lots <span style="font-weight:400; color:#aaa">(Avg: €${p.data.avg_price.toFixed(2)})</span></span>
                    </div>`;
          }
        });
        res += '</div>';
        return res;
      }
    },
    legend: { textStyle: { color: 'var(--text-secondary)' }, bottom: 0, type: 'scroll' },
    grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
    xAxis: { type: 'value', axisLabel: { color: 'var(--text-secondary)' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    yAxis: { type: 'category', data: topNatData.map(b => `${b.maison} - ${b.tipologia}`), axisLabel: { color: 'var(--text-secondary)', width: 140, overflow: 'truncate', fontSize: 10 } },
    series: seriesData
  };

  const availableTipologie = deepHierarchy.find(m => m.name === deepMaison)?.tipologie || [];
  const availableVintagesData = availableTipologie.find(t => t.name === deepTipologia)?.annate || [];
  const availableVintages = availableVintagesData.map(v => v.name);
  const availableFormati = availableVintagesData.find(v => v.name === deepVintage)?.formati || [];

  const getDeepVolumeOption = () => {
    if (!deepBottleData || !deepBottleData.nationalities) return {};
    const nats = [...deepBottleData.nationalities].sort((a,b) => a.lots_won - b.lots_won); // ascending for vertical chart
    return {
      backgroundColor: 'transparent',
      tooltip: { formatter: (p) => `${p.name}: ${p.value} lots` },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
      yAxis: { type: 'category', data: nats.map(n => n.country), axisLabel: { color: 'var(--text-secondary)' } },
      series: [{ type: 'bar', data: nats.map(n => ({ value: n.lots_won, itemStyle: { color: '#c5a059' } })) }]
    };
  };

  const getDeepValueOption = () => {
    if (!deepBottleData || !deepBottleData.nationalities) return {};
    const nats = [...deepBottleData.nationalities].sort((a,b) => a.avg_price - b.avg_price);
    return {
      backgroundColor: 'transparent',
      tooltip: { formatter: (p) => `${p.name}: €${p.value.toFixed(2)} average` },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'value', axisLabel: { formatter: '€{value}' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
      yAxis: { type: 'category', data: nats.map(n => n.country), axisLabel: { color: 'var(--text-secondary)' } },
      series: [{ type: 'bar', data: nats.map(n => ({ value: n.avg_price, itemStyle: { color: '#2ecc71' } })) }]
    };
  };

  const getDeepTrendOption = () => {
    if (!deepBottleData || !deepBottleData.history) return {};
    const history = [...deepBottleData.history].sort((a,b) => a.date.localeCompare(b.date));
    return {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis', formatter: (params) => {
        const p = params[0];
        const data = history[p.dataIndex];
        return `${data.date}<br/>Price: <b>€${data.price.toLocaleString()}</b><br/>Box: ${data.has_box ? 'Yes' : 'No'}`;
      }},
      grid: { left: '3%', right: '4%', bottom: '10%', top: '10%', containLabel: true },
      xAxis: { 
        type: 'category', 
        data: history.map(h => h.date.split(' ')[0]), 
        axisLabel: { color: 'var(--text-secondary)', rotate: 45 },
        splitLine: { show: false }
      },
      yAxis: { 
        type: 'value', 
        axisLabel: { color: 'var(--text-secondary)', formatter: '€{value}' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
      },
      series: [{
        type: 'line',
        data: history.map(h => h.price),
        smooth: true,
        symbolSize: 8,
        itemStyle: { color: '#c5a059' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: 'rgba(197, 160, 89, 0.3)' }, { offset: 1, color: 'rgba(197, 160, 89, 0)' }]
          }
        },
        markPoint: {
          data: [
            { type: 'max', name: 'Max', itemStyle: { color: '#e74c3c' } },
            { type: 'min', name: 'Min', itemStyle: { color: '#2ecc71' } }
          ]
        },
        markLine: {
          data: [{ type: 'average', name: 'Avg', lineStyle: { color: '#3498db', type: 'dashed' } }]
        }
      }]
    };
  };

  const getDeepScatterOption = () => {
    if (!deepBottleData || !deepBottleData.history) return {};
    const history = [...deepBottleData.history].sort((a,b) => a.date.localeCompare(b.date));
    const dates = history.map(h => h.date.split(' ')[0]);
    
    const withBoxData = history.filter(h => h.has_box).map(h => [h.date.split(' ')[0], h.price]);
    const withoutBoxData = history.filter(h => !h.has_box).map(h => [h.date.split(' ')[0], h.price]);

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        formatter: function (params) {
          return `${params.marker} <b>${params.seriesName}</b><br/>Date: ${params.value[0]}<br/>Price: <b>€${params.value[1].toLocaleString()}</b>`;
        }
      },
      legend: {
        data: [{name: 'Con Box'}, {name: 'Senza Box'}],
        textStyle: { color: 'var(--text-secondary)' },
        top: 0
      },
      grid: { left: '3%', right: '4%', bottom: '10%', top: '15%', containLabel: true },
      xAxis: {
        type: 'category',
        data: [...new Set(dates)],
        axisLabel: { color: 'var(--text-secondary)', rotate: 45 },
        splitLine: { show: false }
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: 'var(--text-secondary)', formatter: '€{value}' },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } },
        scale: true
      },
      series: [
        {
          name: 'Con Box',
          type: 'scatter',
          itemStyle: { color: '#2ecc71', opacity: 0.8 },
          symbolSize: 12,
          data: withBoxData
        },
        {
          name: 'Senza Box',
          type: 'scatter',
          itemStyle: { color: '#e74c3c', opacity: 0.8 },
          symbolSize: 12,
          data: withoutBoxData
        }
      ]
    };
  };

  const renderStabilityAnalysis = () => {
    if (!deepBottleData || !deepBottleData.history || deepBottleData.history.length < 2) return null;
    
    const prices = deepBottleData.history.map(h => h.price);
    const n = prices.length;
    const mean = prices.reduce((a, b) => a + b, 0) / n;
    
    const sortedPrices = [...prices].sort((a,b) => a - b);
    const mid = Math.floor(n / 2);
    const median = n % 2 !== 0 ? sortedPrices[mid] : (sortedPrices[mid - 1] + sortedPrices[mid]) / 2;

    const squareDiffs = prices.map(value => {
      const diff = value - mean;
      return diff * diff;
    });
    const avgSquareDiff = squareDiffs.reduce((a, b) => a + b, 0) / n;
    const stdDev = Math.sqrt(avgSquareDiff);
    
    const cv = (stdDev / mean) * 100;
    
    let stabilityText = "";
    let stabilityColor = "";
    if (cv < 15) {
      stabilityText = "Alta (Basso Rischio)";
      stabilityColor = "#2ecc71";
    } else if (cv < 30) {
      stabilityText = "Media (Rischio Moderato)";
      stabilityColor = "#f39c12";
    } else {
      stabilityText = "Bassa (Alta Volatilità)";
      stabilityColor = "#e74c3c";
    }

    return (
      <div style={{ gridColumn: 'span 2', background: 'rgba(52, 152, 219, 0.05)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(52, 152, 219, 0.2)', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
          <div>
            <h4 style={{ color: '#3498db', display: 'flex', alignItems: 'center', gap: '8px', margin: 0, fontSize: '1.1rem' }}>
              <TrendingUp size={20} />
              Analisi di Stabilità del Valore (Volatilità)
            </h4>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '4px' }}>
              Misura della dispersione dei prezzi di chiusura. Una deviazione standard bassa indica prezzi costanti e prevedibili.
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Stabilità</span>
            <div style={{ fontSize: '1.2rem', fontWeight: '700', color: stabilityColor }}>{stabilityText}</div>
            <span style={{ fontSize: '0.8rem', color: stabilityColor, fontWeight: '600' }}>Indice CV: {cv.toFixed(1)}%</span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Media Prezzi (Mean)</span>
            <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'white', marginTop: '4px' }}>€{mean.toFixed(2)}</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '8px' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Mediana (Median)</span>
            <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'white', marginTop: '4px' }}>€{median.toFixed(2)}</div>
          </div>
          <div style={{ background: 'rgba(52, 152, 219, 0.1)', padding: '1rem', borderRadius: '8px', border: '1px dashed rgba(52, 152, 219, 0.4)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Info size={14} color="#3498db" />
              <span style={{ fontSize: '0.7rem', color: '#3498db', fontWeight: '700', textTransform: 'uppercase' }}>Deviazione Standard (σ)</span>
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: '700', color: '#3498db', marginTop: '4px' }}>±€{stdDev.toFixed(2)}</div>
            <div style={{ fontSize: '0.6rem', color: 'var(--text-secondary)', marginTop: '4px', lineHeight: '1.2' }}>Prezzo tipico atteso: tra €{Math.max(0, mean - stdDev).toFixed(0)} e €{(mean + stdDev).toFixed(0)}.</div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="analysis-view">
      <div className="dashboard-grid" style={{ padding: 0 }}>
        <div className="glass-card" style={{ gridColumn: 'span 2' }}>
          <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <BarChart size={20} color="var(--accent-gold)" />
            Price Performance by Maison
          </h3>
          <ReactECharts option={priceOption} style={{ height: '600px' }} />
        </div>

        <div className="glass-card" style={{ gridColumn: 'span 2', marginTop: '2rem' }}>
          <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <MapPin size={20} color="var(--accent-gold)" />
            Bidder Nationalities by Maison
          </h3>
          
          <div style={{ marginBottom: '1rem' }}>
            <select 
              value={selectedMaison} 
              onChange={(e) => setSelectedMaison(e.target.value)}
              style={{
                backgroundColor: 'var(--bg-secondary)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-color)',
                borderRadius: '6px',
                padding: '8px 12px',
                fontSize: '14px'
              }}
            >
              <option value="">Select Maison</option>
              {Object.keys(nationalityData).map(maison => (
                <option key={maison} value={maison}>{maison}</option>
              ))}
            </select>
          </div>

          {natLoading ? (
            <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
              Loading nationality data...
            </div>
          ) : (
            <>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                Solo lotti chiusi e venduti con nazionalità del vincitore nota. Clicca su una fetta per vedere i lotti.
              </p>
              <ReactECharts option={nationalityOption} onEvents={nationalityEvents} style={{ height: '500px' }} />
            </>
          )}
        </div>

        {/* Global Leadership by Most Traded Bottles */}
        <div className="glass-card" style={{ gridColumn: 'span 2', marginTop: '2rem' }}>
          <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <MapPin size={20} color="var(--accent-gold)" />
            Global Leadership by Most Traded Bottles
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1rem' }}>
            A ranking of the winning nationalities for the top most traded Champagne bottles. 
            Hover over the segments to see the exact number of lots won and the average price paid by each country.
            Click a segment to see the lots behind it.
          </p>

          {topNatLoading ? (
            <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
              Loading top traded bottles leadership data...
            </div>
          ) : (
            <ReactECharts option={topNatOption} onEvents={topNatEvents} style={{ height: '500px' }} />
          )}
        </div>

        {/* Deep Dive Section */}
        <div className="glass-card" style={{ gridColumn: 'span 2', marginTop: '2rem' }}>
          <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <MapPin size={20} color="var(--accent-gold)" />
            Deep Dive: Explore Specific Bottle Demographics
          </h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '1.5rem' }}>
            Select a specific Maison, Tipologia, Vintage, and Formato to find out who are the best bidders for that exact bottle.
          </p>

          <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
            <select 
              value={deepMaison} 
              onChange={(e) => { setDeepMaison(e.target.value); setDeepTipologia(''); setDeepVintage(''); setDeepFormato(''); }}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px 12px' }}
            >
              <option value="">Select Maison</option>
              {deepHierarchy.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ))}
            </select>
            
            <select 
              value={deepTipologia} 
              onChange={(e) => { setDeepTipologia(e.target.value); setDeepVintage(''); setDeepFormato(''); }}
              disabled={!deepMaison}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px 12px' }}
            >
              <option value="">Select Tipologia</option>
              {availableTipologie.map(t => (
                <option key={t.name} value={t.name}>{t.name}</option>
              ))}
            </select>
            
            <select 
              value={deepVintage} 
              onChange={(e) => { setDeepVintage(e.target.value); setDeepFormato(''); }}
              disabled={!deepTipologia}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px 12px' }}
            >
              <option value="">Select Vintage</option>
              {availableVintages.map(v => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>

            <select 
              value={deepFormato} 
              onChange={(e) => setDeepFormato(e.target.value)}
              disabled={!deepVintage}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '8px 12px' }}
            >
              <option value="">Select Formato</option>
              {availableFormati.map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>

            <select 
              value={deepHasBox} 
              onChange={(e) => setDeepHasBox(e.target.value)}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--accent-gold)', border: '1px solid var(--accent-gold)', borderRadius: '6px', padding: '8px 12px', fontWeight: '600' }}
            >
              <option value="all">Box: All</option>
              <option value="yes">Box: Yes Only</option>
              <option value="no">Box: No Only</option>
            </select>

            <select 
              value={deepFilterMode} 
              onChange={(e) => setDeepFilterMode(e.target.value)}
              style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--accent-gold)', border: '1px solid var(--accent-gold)', borderRadius: '6px', padding: '8px 12px', fontWeight: '600' }}
            >
              <option value="all">Filtro Lotto: Tutti</option>
              <option value="pure">Filtro Lotto: Linee Pure</option>
              <option value="mixed">Filtro Lotto: Lotti Misti</option>
            </select>
          </div>

          {deepLoading ? (
            <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>Loading bottle demographics...</div>
          ) : !deepBottleData || !deepBottleData.nationalities ? (
            <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem', opacity: 0.5 }}>
              Select a Maison, Tipologia, Vintage, and Formato to view its dedicated analytics.
            </div>
          ) : deepBottleData.nationalities.length === 0 ? (
            <div style={{ color: 'var(--text-secondary)', textAlign: 'center', padding: '2rem' }}>
              No closed auction data available for this bottle.
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
              {renderStabilityAnalysis()}
              {deepBottleData.box_analysis && deepBottleData.box_analysis.sample_size_with > 0 && deepBottleData.box_analysis.sample_size_without > 0 && (
                <div style={{ gridColumn: 'span 2', background: 'rgba(197, 160, 89, 0.05)', padding: '1.5rem', borderRadius: '12px', border: '1px solid rgba(197, 160, 89, 0.2)', marginBottom: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div>
                      <h4 style={{ color: '#c5a059', display: 'flex', alignItems: 'center', gap: '8px', margin: 0, fontSize: '1.1rem' }}>
                        <Package size={20} />
                        Box Profitability Analysis
                      </h4>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', marginTop: '4px' }}>
                        Pairing a box with a "nude" bottle to increase its market value.
                      </p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Premium Medio</span>
                      <div style={{ fontSize: '1.5rem', fontWeight: '700', color: '#2ecc71' }}>+€{deepBottleData.box_analysis.premium_abs.toLocaleString()}</div>
                      <span style={{ fontSize: '0.8rem', color: '#2ecc71', fontWeight: '600' }}>({deepBottleData.box_analysis.premium_pct}%)</span>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '8px' }}>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Media CON Box</span>
                      <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'white', marginTop: '4px' }}>€{deepBottleData.box_analysis.avg_with_box.toLocaleString()}</div>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>Su {deepBottleData.box_analysis.sample_size_with} lotti</span>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: '8px' }}>
                      <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Media SENZA Box</span>
                      <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'white', marginTop: '4px' }}>€{deepBottleData.box_analysis.avg_without_box.toLocaleString()}</div>
                      <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>Su {deepBottleData.box_analysis.sample_size_without} lotti</span>
                    </div>
                    <div style={{ background: 'rgba(197, 160, 89, 0.1)', padding: '1rem', borderRadius: '8px', border: '1px dashed rgba(197, 160, 89, 0.4)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <TrendingUp size={14} color="#c5a059" />
                        <span style={{ fontSize: '0.7rem', color: '#c5a059', fontWeight: '700', textTransform: 'uppercase' }}>Max Prezzo al Venditore Box</span>
                      </div>
                      <div style={{ fontSize: '1.1rem', fontWeight: '700', color: '#c5a059', marginTop: '4px' }}>€{deepBottleData.box_analysis.max_box_buy_price.toLocaleString()}</div>
                      <div style={{ fontSize: '0.6rem', color: 'var(--text-secondary)', marginTop: '2px', lineHeight: '1.2' }}>Pagando questa cifra o meno, manterrai un margine di profitto sull'operazione.</div>
                    </div>
                  </div>
                </div>
              )}
              <div>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>LOTS WON BY NATIONALITY (VOLUME)</p>
                <ReactECharts option={getDeepVolumeOption()} style={{ height: '300px' }} />
              </div>
              <div>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>AVERAGE PRICE PAID (VALUE)</p>
                <ReactECharts option={getDeepValueOption()} style={{ height: '300px' }} />
              </div>
              <div style={{ gridColumn: 'span 2', marginTop: '1rem' }}>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>CHRONOLOGICAL PRICE TREND</p>
                <ReactECharts option={getDeepTrendOption()} style={{ height: '350px' }} />
              </div>
              <div style={{ gridColumn: 'span 2', marginTop: '1rem' }}>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>SCATTER PLOT: CORRELAZIONE VALORE CON BOX VS SENZA BOX</p>
                <ReactECharts option={getDeepScatterOption()} style={{ height: '400px' }} />
              </div>
            </div>
          )}
        </div>
      </div>

      <NationalityDrillThrough
        drill={drill}
        onClose={closeDrill}
        fields={{ group: 'maison', groupLabel: 'Maison', type: 'tipologia', typeLabel: 'Tipologia', age: 'vintage', ageLabel: 'Annata' }}
      />
    </div>
  );
};

export default AnalysisView;

import React, { useState, useEffect, useCallback } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, Filter, RefreshCw, AlertCircle, BarChart3 } from 'lucide-react';
import axios from 'axios';

export default function Dashboard() {
  // State for hierarchy
  const [maisons, setMaisons] = useState([]);
  const [tipologie, setTipologie] = useState([]);
  const [annate, setAnnate] = useState([]);
  const [formati, setFormati] = useState([]);

  // State for selections
  const [selectedMaison, setSelectedMaison] = useState('');
  const [selectedTipologia, setSelectedTipologia] = useState('');
  const [selectedVintage, setSelectedVintage] = useState('');
  const [selectedFormato, setSelectedFormato] = useState('');
  const [mode, setMode] = useState('both'); // both, mean, median

  // State for data
  const [statsData, setStatsData] = useState([]);
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load hierarchy on mount
  useEffect(() => {
    const loadHierarchy = async () => {
      try {
        const response = await axios.get('/api/analysis/hierarchy');
        setMaisons(response.data || []);
      } catch (err) {
        console.error('Error loading hierarchy:', err);
        setError('Errore nel caricamento della gerarchia');
      }
    };

    loadHierarchy();
  }, []);

  // Update tipologie when maison changes
  useEffect(() => {
    if (selectedMaison) {
      const maison = maisons.find(m => m.name === selectedMaison);
      setTipologie(maison?.tipologie || []);
      setSelectedTipologia('');
      setSelectedVintage('');
    } else {
      setTipologie([]);
      setAnnate([]);
    }
  }, [selectedMaison, maisons]);

  // Update annate when tipologia changes
  useEffect(() => {
    if (selectedTipologia && tipologie.length > 0) {
      const tipo = tipologie.find(t => t.name === selectedTipologia);
      setAnnate(tipo?.annate || []);
      setSelectedVintage('');
      setSelectedFormato('');
    } else {
      setAnnate([]);
      setFormati([]);
    }
  }, [selectedTipologia, tipologie]);

  // Update formati when vintage changes
  useEffect(() => {
    if (selectedVintage && annate.length > 0) {
      const annataObj = annate.find(a => a.name === selectedVintage);
      setFormati(annataObj?.formati || []);
      setSelectedFormato('');
    } else {
      setFormati([]);
    }
  }, [selectedVintage, annate]);

  const fetchStats = useCallback(async () => {
    // Prevent multiple simultaneous requests and require at least maison
    if (loading || !selectedMaison) return;
    
    setLoading(true);
    setError(null);

    try {
      const params = { maison: selectedMaison };
      if (selectedTipologia) params.tipologia = selectedTipologia;
      if (selectedVintage) params.vintage = selectedVintage;
      if (selectedFormato) params.formato = selectedFormato;

      const response = await axios.get('/api/analysis/stats', { params });
      setStatsData(response.data || []);
      
      // Small delay to prevent rapid re-renders and layout shifts
      setTimeout(() => {
        setLoading(false);
      }, 150);
    } catch (err) {
      console.error('Error fetching stats:', err);
      setError('Errore nel caricamento delle statistiche');
      setStatsData([]);
      setLoading(false);
    }
  }, [selectedMaison, selectedTipologia, selectedVintage, selectedFormato, loading]);

  const fetchPrediction = async () => {
    if (!selectedMaison) {
      setError('Seleziona una Maison prima');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const params = { maison: selectedMaison };
      if (selectedTipologia) params.tipologia = selectedTipologia;
      if (selectedVintage) params.vintage = selectedVintage;
      if (selectedFormato) params.formato = selectedFormato;

      const response = await axios.get('/api/analysis/predict', { params });
      setPrediction(response.data);
    } catch (err) {
      console.error('Error fetching prediction:', err);
      setError('Errore nella previsione');
      setPrediction(null);
    } finally {
      setLoading(false);
    }
  };



  return (
    <div className="bottle-detail animate-fade-in" style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 className="font-outfit" style={{ fontSize: '2.4rem', marginBottom: '2rem', letterSpacing: '-1px' }}>
        🍾 Wine Investment Dashboard
      </h1>

      {/* FILTERS SECTION */}
      <div className="glass-card" style={{ padding: '2rem', marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.2rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Filter size={20} /> Filter & Analysis
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
          {/* Maison Select */}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '600' }}>
              Maison
            </label>
            <select 
              value={selectedMaison}
              onChange={(e) => setSelectedMaison(e.target.value)}
              className="dashboard-select"
            >
              <option value="">Select Maison...</option>
              {maisons.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              ))}
            </select>
          </div>

          {/* Tipologia Select */}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '600' }}>
              Tipologia
            </label>
            <select 
              value={selectedTipologia}
              onChange={(e) => setSelectedTipologia(e.target.value)}
              disabled={!selectedMaison}
              className="dashboard-select"
            >
              <option value="">All Tipologie</option>
              {tipologie.map(t => (
                <option key={t.name} value={t.name}>{t.name}</option>
              ))}
            </select>
          </div>

          {/* Vintage Select */}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '600' }}>
              Vintage / Annata
            </label>
            <select 
              value={selectedVintage}
              onChange={(e) => setSelectedVintage(e.target.value)}
              disabled={!selectedTipologia}
              className="dashboard-select"
            >
              <option value="">All Vintages</option>
              {annate.map(a => (
                <option key={a.name} value={a.name}>{a.name}</option>
              ))}
            </select>
          </div>

          {/* Formato Select */}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '600' }}>
              Formato
            </label>
            <select 
              value={selectedFormato}
              onChange={(e) => setSelectedFormato(e.target.value)}
              disabled={!selectedVintage}
              className="dashboard-select"
            >
              <option value="">All Formats</option>
              {formati.map(f => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </div>

          {/* Mode Select */}
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem', fontWeight: '600' }}>
              Chart Mode
            </label>
            <select 
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="dashboard-select"
            >
              <option value="both">Mean + Median</option>
              <option value="mean">Mean Only</option>
              <option value="median">Median Only</option>
            </select>
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <button 
            onClick={fetchStats}
            disabled={!selectedMaison || loading}
            style={{
              background: selectedMaison ? 'var(--accent-gold)' : 'rgba(197, 160, 89, 0.3)',
              color: selectedMaison ? '#000' : 'var(--text-secondary)',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '8px',
              fontWeight: '600',
              cursor: selectedMaison && !loading ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              transition: 'all 0.2s ease',
              opacity: loading ? 0.7 : 1,
              pointerEvents: loading ? 'none' : 'auto'
            }}
          >
            {loading ? <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <BarChart3 size={18} />}
            {loading ? 'Loading Data...' : 'Load & Update Chart'}
          </button>

          <button 
            onClick={fetchPrediction}
            disabled={!selectedMaison}
            style={{
              background: 'rgba(46, 204, 113, 0.2)',
              color: '#2ecc71',
              border: '1px solid rgba(46, 204, 113, 0.5)',
              padding: '10px 20px',
              borderRadius: '8px',
              fontWeight: '600',
              cursor: selectedMaison ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              opacity: selectedMaison ? 1 : 0.5
            }}
          >
            <TrendingUp size={18} />
            Price Prediction
          </button>
        </div>

        {error && (
          <div style={{ marginTop: '1.5rem', padding: '1rem', background: 'rgba(255, 77, 77, 0.1)', border: '1px solid rgba(255, 77, 77, 0.3)', borderRadius: '8px', display: 'flex', gap: '8px', alignItems: 'center', color: '#ff4d4d' }}>
            <AlertCircle size={20} />
            {error}
          </div>
        )}
      </div>

      {/* CHART SECTION */}
      {statsData.length > 0 && (
        <div className="glass-card chart-container" style={{ padding: '2rem', marginBottom: '2rem' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '1.5rem' }}>
            📈 Price Trends - {selectedMaison} {selectedTipologia && `/ ${selectedTipologia}`}
          </h2>

          {statsData.length < 3 && (
            <div style={{ 
              background: 'rgba(197, 160, 89, 0.1)', 
              border: '1px solid rgba(197, 160, 89, 0.3)', 
              padding: '1rem', 
              borderRadius: '8px', 
              marginBottom: '1.5rem',
              fontSize: '0.9rem',
              color: 'var(--text-secondary)'
            }}>
              ⚠️ Limited data available ({statsData.length} data points). Trends may not be statistically significant.
            </div>
          )}

          <div style={{ width: '100%', height: '400px', position: 'relative' }}>
            <ResponsiveContainer width="100%" height="100%" key={`chart-${selectedMaison}-${selectedTipologia}-${selectedVintage}`}>
              <LineChart data={statsData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                <XAxis 
                  dataKey="data" 
                  stroke="var(--text-secondary)" 
                  style={{ fontSize: '12px' }}
                  tickFormatter={(val) => val.substring(5)} // Show MM-DD only
                />
                <YAxis 
                  stroke="var(--text-secondary)"
                  style={{ fontSize: '12px' }}
                  tickFormatter={(val) => `€${val}`}
                  width={60}
                />
                <Tooltip 
                  contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}
                  formatter={(value) => `€${value.toFixed(2)}`}
                />
                <Legend />

                {(mode === 'both' || mode === 'mean') && (
                  <Line 
                    type="monotone" 
                    dataKey="mean" 
                    name="Mean (Average)" 
                    stroke="var(--accent-gold)" 
                    dot={{ r: 4, fill: 'var(--accent-gold)' }}
                    activeDot={{ r: 6 }}
                    strokeWidth={2}
                  />
                )}

                {(mode === 'both' || mode === 'median') && (
                  <Line 
                    type="monotone" 
                    dataKey="median" 
                    name="Median" 
                    stroke="rgba(46, 204, 113, 0.7)" 
                    dot={{ r: 4 }}
                    activeDot={{ r: 6 }}
                    strokeWidth={2}
                    strokeDasharray="5 5"
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* PREDICTION SECTION */}
      {prediction && (
        <div className="glass-card" style={{ padding: '2rem', marginBottom: '2rem', border: '1px solid var(--accent-gold)', background: 'linear-gradient(135deg, rgba(197, 160, 89, 0.1) 0%, rgba(0,0,0,0) 100%)' }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '1.5rem', color: 'var(--accent-gold)' }}>
            🔮 AI Price Prediction
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
            {/* Predicted Price */}
            <div className="glass-card" style={{ padding: '1.5rem' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>PREDICTED PRICE</p>
              <h3 style={{ fontSize: '2rem', fontWeight: '800', color: 'var(--accent-gold)' }}>
                €{prediction.prediction?.toFixed(2) || 'N/A'}
              </h3>
            </div>

            {/* Confidence */}
            <div className="glass-card" style={{ padding: '1.5rem' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>CONFIDENCE</p>
              <div style={{ display: 'flex', gap: '4px', marginTop: '0.5rem' }}>
                {[1, 2, 3, 4, 5].map(i => (
                  <span 
                    key={i} 
                    style={{ 
                      width: '20px', 
                      height: '6px', 
                      borderRadius: '10px', 
                      background: i <= (prediction.confidence || 0) ? 'var(--accent-gold)' : 'rgba(255,255,255,0.1)' 
                    }}
                  />
                ))}
              </div>
              <p style={{ fontSize: '0.85rem', marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                Score: {(prediction.confidence_score * 100).toFixed(1)}%
              </p>
            </div>

            {/* Strategy */}
            <div className="glass-card" style={{ padding: '1.5rem' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>STRATEGY</p>
              <h3 style={{ 
                fontSize: '1.4rem', 
                fontWeight: '800',
                color: prediction.strategy === 'BUY' ? '#2ecc71' : prediction.strategy === 'HOLD' ? 'var(--accent-gold)' : '#e74c3c'
              }}>
                {prediction.strategy}
              </h3>
              <p style={{ fontSize: '0.7rem', marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                {prediction.trend}
              </p>
            </div>

            {/* Market Stats */}
            <div className="glass-card" style={{ padding: '1.5rem' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '0.5rem' }}>MARKET DATA</p>
              <p style={{ fontSize: '0.9rem', marginBottom: '4px' }}>Current Avg: <span style={{ fontWeight: '700' }}>€{prediction.current_avg}</span></p>
              <p style={{ fontSize: '0.9rem', marginBottom: '4px' }}>Range: <span style={{ fontWeight: '700' }}>€{prediction.price_range?.min} - €{prediction.price_range?.max}</span></p>
              <p style={{ fontSize: '0.9rem' }}>Data Points: <span style={{ fontWeight: '700' }}>{prediction.num_data_points}</span></p>
            </div>
          </div>

          {prediction.strategy === 'BUY' && (
            <div style={{ background: 'rgba(46, 204, 113, 0.1)', border: '1px solid rgba(46, 204, 113, 0.3)', padding: '1rem', borderRadius: '8px', color: '#2ecc71', fontSize: '0.95rem' }}>
              ✅ Strong uptrend detected. Prices are likely to increase. Recommended action: PURCHASE
            </div>
          )}
          {prediction.strategy === 'HOLD' && (
            <div style={{ background: 'rgba(197, 160, 89, 0.1)', border: '1px solid rgba(197, 160, 89, 0.3)', padding: '1rem', borderRadius: '8px', color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
              ⏸️  Moderate trend detected. Market conditions are stable. Recommended action: MONITOR & EVALUATE
            </div>
          )}
          {prediction.strategy === 'AVOID' && (
            <div style={{ background: 'rgba(255, 77, 77, 0.1)', border: '1px solid rgba(255, 77, 77, 0.3)', padding: '1rem', borderRadius: '8px', color: '#ff4d4d', fontSize: '0.95rem' }}>
              ⚠️  Weak trend detected. Insufficient data for confident prediction. Recommended action: AVOID OR WAIT FOR MORE DATA
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {statsData.length === 0 && !prediction && selectedMaison && (
        <div className="glass-card" style={{ padding: '4rem 2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <BarChart3 size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
          <h3 style={{ marginBottom: '0.5rem' }}>No Price Data Available</h3>
          <p>This champagne house doesn't have enough closed auctions with price data yet.</p>
          <p style={{ fontSize: '0.9rem', marginTop: '1rem', opacity: 0.7 }}>
            Try selecting a different Maison or check back later as more auctions complete.
          </p>
        </div>
      )}

      {!selectedMaison && (
        <div className="glass-card" style={{ padding: '4rem 2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
          <AlertCircle size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
          <h3 style={{ marginBottom: '0.5rem' }}>Select a Maison to Begin</h3>
          <p>Choose a champagne house from the dropdown above to analyze price trends and get AI predictions</p>
        </div>
      )}
    </div>
  );
}

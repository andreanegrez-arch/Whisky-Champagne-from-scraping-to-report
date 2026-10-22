import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Play, Activity, Clock, Server, CheckCircle2, Cloud } from 'lucide-react';

const SettingsView = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [pullMessage, setPullMessage] = useState(null);
  const [error, setError] = useState(null);

  const fetchStatus = async () => {
    try {
      const response = await axios.get('/api/scraper/status');
      setStatus(response.data);
    } catch (err) {
      console.error('Error fetching scraper status:', err);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchStatus();
    
    // Poll every 2 seconds
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const startScraper = async () => {
    try {
      setLoading(true);
      setPullMessage(null);
      setError(null);
      await axios.post('/api/scraper/start');
      fetchStatus();
    } catch (err) {
      setError(err.response?.data?.message || err.message);
    } finally {
      setLoading(false);
    }
  };

  const pullFromCloud = async () => {
    try {
      setPulling(true);
      setPullMessage(null);
      setError(null);
      const response = await axios.post('/api/scraper/pull');
      setPullMessage(response.data.message);
      fetchStatus();
    } catch (err) {
      setError(err.response?.data?.error || err.response?.data?.message || err.message);
    } finally {
      setPulling(false);
    }
  };

  const isRunning = status?.is_running;
  const progress = status?.progress || 0;
  const message = status?.message || "Idle";
  const lastRun = status?.last_run ? new Date(status.last_run).toLocaleString() : "Never";

  return (
    <div className="settings-view animate-fade-in">
      <div className="glass-card" style={{ padding: '2rem', marginBottom: '2rem' }}>
        <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Server size={20} color="var(--accent-color)" />
          Scraper Engine Control Panel
        </h3>
        
        <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
          Manage the data extraction pipeline directly from this interface. 
          The scraper autonomously browses Catawiki to fetch the latest Whisky auction data, calculates historical trends, and triggers Telegram alerts for undervalued lots.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
          <div className="glass-card" style={{ padding: '1.5rem', background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              <Activity size={18} /> Engine Status
            </div>
            <div style={{ fontSize: '1.2rem', fontWeight: '600', color: isRunning ? '#3498db' : 'var(--accent-color)' }}>
              {isRunning ? 'RUNNING' : 'STANDING BY'}
            </div>
          </div>
          
          <div className="glass-card" style={{ padding: '1.5rem', background: 'rgba(255,255,255,0.02)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
              <Clock size={18} /> Last Workflow Run
            </div>
            <div style={{ fontSize: '1.2rem', fontWeight: '600' }}>
              {lastRun}
            </div>
          </div>
        </div>

        <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '12px', padding: '1.5rem', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <span style={{ color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
              {'>'} {message}
            </span>
            <span style={{ fontWeight: '600', color: 'var(--accent-color)' }}>
              {progress.toFixed(1)}%
            </span>
          </div>
          
          {/* Progress Bar */}
          <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
            <div 
              style={{ 
                width: `${progress}%`, 
                height: '100%', 
                background: isRunning ? '#3498db' : (progress === 100 ? '#2ecc71' : 'var(--accent-color)'),
                transition: 'width 0.5s ease-out, background 0.5s ease-out'
              }} 
            />
          </div>
        </div>

        {error && (
          <div style={{ color: '#e74c3c', marginBottom: '1.5rem', padding: '1rem', background: 'rgba(231,76,60,0.1)', borderRadius: '8px' }}>
            ⚠️ {error}
          </div>
        )}

        {pullMessage && (
          <div style={{ color: '#2ecc71', marginBottom: '1.5rem', padding: '1rem', background: 'rgba(46,204,113,0.1)', borderRadius: '8px' }}>
            ✅ {pullMessage}
          </div>
        )}

        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <button 
            className="btn-primary" 
            onClick={startScraper}
            disabled={isRunning || loading || pulling}
            style={{ 
              display: 'flex', alignItems: 'center', gap: '10px', 
              padding: '12px 24px', fontSize: '1.1rem',
              opacity: (isRunning || loading || pulling) ? 0.5 : 1,
              cursor: (isRunning || loading || pulling) ? 'not-allowed' : 'pointer',
              background: isRunning ? 'rgba(255,255,255,0.1)' : 'var(--accent-color)',
              flex: '1'
            }}
          >
            {isRunning ? <Activity size={20} className="animate-pulse" /> : <Play size={20} />}
            {isRunning ? 'Scraping in Corso...' : 'Avvia Scraper Locale'}
          </button>

          <button 
            onClick={pullFromCloud}
            disabled={isRunning || loading || pulling}
            style={{ 
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', 
              padding: '12px 24px', fontSize: '1.1rem',
              opacity: (isRunning || loading || pulling) ? 0.5 : 1,
              cursor: (isRunning || loading || pulling) ? 'not-allowed' : 'pointer',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'white',
              borderRadius: '8px',
              flex: '1',
              fontWeight: 500,
              transition: 'background 0.2s'
            }}
            onMouseOver={(e) => !pulling && (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
            onMouseOut={(e) => !pulling && (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
          >
            {pulling ? <Activity size={20} className="animate-pulse" /> : <Cloud size={20} />}
            {pulling ? 'Sincronizzazione...' : 'Sincronizza Dal Cloud'}
          </button>
        </div>
      </div>
      
      <div className="glass-card" style={{ padding: '2rem' }}>
         <h3 className="font-outfit" style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <CheckCircle2 size={20} color="#2ecc71" />
          Scheduled Automations
        </h3>
        <ul style={{ color: 'var(--text-secondary)', paddingLeft: '1.5rem', lineHeight: '1.8' }}>
            <li><strong>Data Refresh:</strong> GitHub Actions configured to run automatically at 03:00 and 17:00 UTC daily.</li>
            <li><strong>Telegram Alerts:</strong> Active. The engine will notify you of undervalued active lots matching the risk thresholds immediately after every scan.</li>
            <li><strong>Market Insights:</strong> Automatically regenerates the SQLite Analytics Models.</li>
        </ul>
      </div>
    </div>
  );
};

export default SettingsView;

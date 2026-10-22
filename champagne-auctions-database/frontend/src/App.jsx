import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LayoutDashboard, Table, BarChart3, RotateCw, Settings, Search, Bell } from 'lucide-react';
import DashboardView from './components/Dashboard';
import InventoryView from './components/Inventory';
import AnalysisView from './components/Analysis';
import BottleDetail from './components/BottleDetail';
import SettingsView from './components/Settings';

// Configurazione axios per il proxy API
axios.defaults.baseURL = '';
axios.defaults.timeout = 30000;

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [lots, setLots] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedLot, setSelectedLot] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      // Prima chiediamo quanti lotti ci sono davvero, poi li richiediamo tutti:
      // niente più tetto fisso che taglia i dati quando il totale cresce.
      const [countRes, statsRes] = await Promise.all([
        axios.get('/api/lots/count'),
        axios.get('/api/analysis/summary')
      ]);
      const totalLots = countRes.data?.count || 0;
      const lotsRes = await axios.get(`/api/lots/?limit=${Math.max(totalLots, 1)}`);
      setLots(lotsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      setError(`Errore nel caricamento dei dati: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectLot = (lot) => {
    setSelectedLot(lot);
    setActiveTab('bottle-detail');
  };

  const handleSync = async () => {
    try {
      setLoading(true);
      setError(null);
      await axios.post('/api/scraper/start');
      alert("Scraper started!");
      setTimeout(fetchData, 5000);
    } catch (error) {
      console.error("Error starting scraper:", error);
      setError(`Scraper error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { id: 'inventory', label: 'Inventory', icon: <Table size={20} /> },
    { id: 'analysis', label: 'Analysis', icon: <BarChart3 size={20} /> },
  ];

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '3rem' }}>
          <div style={{ width: '40px', height: '40px', background: 'var(--accent-gold)', borderRadius: '10px', display: 'grid', placeItems: 'center' }}>
            <span style={{ color: '#000', fontWeight: '800' }}>C</span>
          </div>
          <h2 className="font-outfit" style={{ fontSize: '1.2rem', fontWeight: '700' }}>Catawiki Elite</h2>
        </div>

        <nav>
          {menuItems.map(item => (
            <div 
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`menu-item ${activeTab === item.id ? 'active' : ''}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px',
                margin: '8px 0',
                borderRadius: '10px',
                cursor: 'pointer',
                color: activeTab === item.id ? 'var(--accent-gold)' : 'var(--text-secondary)',
                background: activeTab === item.id ? 'rgba(197, 160, 89, 0.1)' : 'transparent',
                transition: 'all 0.2s'
              }}
            >
              {item.icon}
              <span style={{ fontWeight: '500' }}>{item.label}</span>
            </div>
          ))}
        </nav>

        <div style={{ marginTop: 'auto', paddingTop: '2rem', borderTop: '1px solid var(--glass-border)' }}>
          <div 
             onClick={() => setActiveTab('settings')}
             style={{ display: 'flex', alignItems: 'center', gap: '12px', color: activeTab === 'settings' ? 'var(--accent-gold)' : 'var(--text-secondary)', cursor: 'pointer' }}>
            <Settings size={20} />
            <span>Settings</span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <div>
            <h1 className="font-outfit" style={{ fontSize: '1.8rem' }}>
              {menuItems.find(m => m.id === activeTab)?.label}
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Catawiki Champagne Analytics • {lots.length} lots loaded</p>
          </div>
          
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button className="btn-primary" onClick={handleSync} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <RotateCw size={18} />
              Sync Data
            </button>
            <div className="glass-card" style={{ padding: '8px 12px', borderRadius: '8px', display: 'flex', alignItems: 'center' }}>
              <Bell size={18} color="var(--text-secondary)" />
            </div>
          </div>
        </header>

        {error && (
          <div style={{ background: 'rgba(231, 76, 60, 0.2)', border: '1px solid #e74c3c', color: '#e74c3c', padding: '1rem', borderRadius: '8px', marginBottom: '2rem' }}>
            <strong>❌ Errore API:</strong> {error}
            <br />
            <small style={{ marginTop: '0.5rem', display: 'block', color: '#f0a' }}>Verifica che il backend sia in ascolto su http://127.0.0.1:8001</small>
          </div>
        )}

        {loading && !error && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '3rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', marginBottom: '2rem' }}>
            <p style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>⏳ Caricamento dati dal backend...</p>
            <p style={{ fontSize: '0.85rem' }}>Se questo messaggio persiste per più di 10 secondi, apri la console del browser (F12) per vedere gli errori.</p>
          </div>
        )}

        {!loading && lots.length === 0 && !error && (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', padding: '2rem', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', marginBottom: '2rem' }}>
            <p>Nessun lotto caricato. Controlla che il backend sia in esecuzione.</p>
          </div>
        )}

        {!loading && lots.length > 0 && (
          <>
            {activeTab === 'dashboard' && <DashboardView stats={stats} lots={lots} loading={loading} />}
            {activeTab === 'inventory' && <InventoryView lots={lots} loading={loading} onSelectLot={handleSelectLot} />}
            {activeTab === 'analysis' && <AnalysisView stats={stats} loading={loading} />}
            {activeTab === 'bottle-detail' && <BottleDetail bottle={selectedLot} onBack={() => setActiveTab('inventory')} />}
            {activeTab === 'settings' && <SettingsView />}
          </>
        )}
      </main>
    </div>
  );
};

export default App;

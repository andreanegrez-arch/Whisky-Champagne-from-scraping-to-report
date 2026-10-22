import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, 
  AreaChart, Area, BarChart, Bar, Legend, Cell
} from 'recharts';
import { 
  ArrowLeft, TrendingUp, Info, History, PlayCircle, 
  AlertCircle, Scale, Target, Award, ShoppingBag, ExternalLink, MapPin
} from 'lucide-react';

const BottleDetail = ({ bottle, onBack }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchBottleData = async () => {
      try {
        setLoading(true);
        const response = await axios.get(`/api/analysis/bottle`, {
          params: {
            maison: bottle.maison,
            tipologia: bottle.tipologia,
            vintage: bottle.vintage
          }
        });
        setData(response.data);
      } catch (error) {
        console.error("Error fetching bottle details:", error);
      } finally {
        setLoading(false);
      }
    };

    if (bottle) {
      fetchBottleData();
    }
  }, [bottle]);

  if (loading) return (
    <div className="bottle-detail animate-fade-in">
      <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'var(--accent-gold)', cursor: 'pointer', marginBottom: '1.5rem', fontWeight: '600' }}>
        <ArrowLeft size={18} />
        Back to Inventory
      </button>
      <div style={{ padding: '4rem', textAlign: 'center' }}>
        <div className="loader" style={{ marginBottom: '1rem' }}></div>
        <p style={{ color: 'var(--text-secondary)' }}>Deep-analyzing market trends...</p>
      </div>
    </div>
  );
  
  if (!data) return (
    <div className="bottle-detail animate-fade-in">
      <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'var(--accent-gold)', cursor: 'pointer', marginBottom: '1.5rem', fontWeight: '600' }}>
        <ArrowLeft size={18} />
        Back to Inventory
      </button>
      <div style={{ padding: '4rem', textAlign: 'center', color: 'red' }}>
        <AlertCircle size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
        <h3 style={{ marginBottom: '1rem' }}>Analysis Unavailable</h3>
        <p style={{ color: 'var(--text-secondary)' }}>Unable to load analysis for {bottle?.maison} {bottle?.tipologia} {bottle?.vintage}</p>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '1rem' }}>This might be due to insufficient market data or a temporary issue.</p>
      </div>
    </div>
  );

  // Check if we have meaningful data
  const hasHistory = data.history && data.history.length > 0;
  const hasStats = data.stats && data.stats.lotti_totali > 0;

  const comparisonData = data.comparison ? [
    { name: 'Single Bottle', value: data.comparison.individual_avg },
    { name: 'Bundle (Avg/btl)', value: data.comparison.bundle_avg }
  ] : [];

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const item = payload[0].payload;
      return (
        <div className="glass-card" style={{ padding: '10px', border: '1px solid var(--accent-gold)', background: '#0a0a0a' }}>
          <p style={{ fontWeight: '700', marginBottom: '5px' }}>{label}</p>
          <p style={{ color: 'var(--accent-gold)' }}>Price: €{item.price.toFixed(2)}</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Lot Content: {item.num_bottles} bottle(s)</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Unit Price: €{item.price_per_bottle.toFixed(2)}</p>
          <p style={{ fontSize: '0.7rem', color: 'var(--accent-gold)', marginTop: '8px', fontWeight: 'bold' }}>Click point to open Catawiki ↗</p>
        </div>
      );
    }
    return null;
  };

  const handlePointClick = (data) => {
    if (data && data.activePayload && data.activePayload.length) {
      const url = data.activePayload[0].payload.url;
      if (url) window.open(url, '_blank');
    }
  };

  return (
    <div className="bottle-detail animate-fade-in">
      <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent', border: 'none', color: 'var(--accent-gold)', cursor: 'pointer', marginBottom: '1.5rem', fontWeight: '600' }}>
        <ArrowLeft size={18} />
        Back to Inventory
      </button>

      <div className="detail-header" style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <h2 className="font-outfit" style={{ fontSize: '2.4rem', marginBottom: '0.5rem', letterSpacing: '-1px' }}>{data.maison}</h2>
          <div style={{ display: 'flex', gap: '15px', color: 'var(--text-secondary)', fontSize: '1.1rem' }}>
            <span className="glass-card" style={{ padding: '4px 12px', borderRadius: '20px' }}>{data.tipologia}</span>
            <span className="glass-card" style={{ padding: '4px 12px', borderRadius: '20px' }}>{data.vintage}</span>
          </div>
        </div>
        
        <div style={{ textAlign: 'right' }}>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '5px' }}>MARKET SCORE</p>
          <div style={{ display: 'flex', gap: '4px' }}>
            {[1, 2, 3, 4, 5].map(s => (
              <span key={s} style={{ width: '20px', height: '6px', borderRadius: '10px', background: s <= 4 ? 'var(--accent-gold)' : 'rgba(255,255,255,0.1)' }}></span>
            ))}
          </div>
        </div>
      </div>

      <div className="grid-layout" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '2rem' }}>
        {/* Performance Stats */}
        <div className="glass-card" style={{ padding: '1.5rem', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', right: '-10px', top: '-10px', opacity: 0.1 }}>
            <TrendingUp size={100} color="var(--accent-gold)" />
          </div>
          <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Target size={18} /> Market Performance
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Global Avg.</p>
              <p style={{ fontSize: '1.8rem', fontWeight: '800' }}>€{data.stats.prezzo_medio.toFixed(0)}</p>
            </div>
            <div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Market Vol.</p>
              <p style={{ fontSize: '1.8rem', fontWeight: '800' }}>{data.stats.lotti_totali}</p>
            </div>
            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem' }}>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Floor Price</p>
              <p style={{ fontSize: '1.2rem', fontWeight: '700', color: '#ff4d4d' }}>€{data.stats.prezzo_min.toFixed(0)}</p>
            </div>
            <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: '1rem' }}>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Ceiling Price</p>
              <p style={{ fontSize: '1.2rem', fontWeight: '700', color: '#00cc66' }}>€{data.stats.prezzo_max.toFixed(0)}</p>
            </div>
          </div>
        </div>

        {/* Strategy Optimization */}
        <div className="glass-card" style={{ padding: '1.5rem', border: data.comparison ? '1px solid var(--accent-gold)' : '1px solid var(--glass-border)', background: data.comparison ? 'linear-gradient(135deg, rgba(197, 160, 89, 0.1) 0%, rgba(0,0,0,0) 100%)' : 'rgba(255,255,255,0.02)' }}>
          <h3 style={{ fontSize: '1rem', color: data.comparison ? 'var(--accent-gold)' : 'var(--text-secondary)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Scale size={18} /> Strategy Optimization
          </h3>
          
          {data.comparison ? (
            <>
              <div style={{ display: 'flex', gap: '20px', marginBottom: '1.5rem' }}>
                <div style={{ width: '120px', height: '120px' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={comparisonData}>
                      <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                        {comparisonData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={index === 0 ? 'rgba(255,255,255,0.2)' : 'var(--accent-gold)'} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Yield per bottle:</p>
                  <p style={{ fontSize: '0.9rem', marginBottom: '4px' }}>Single: <span style={{ fontWeight: '700' }}>€{data.comparison.individual_avg}</span></p>
                  <p style={{ fontSize: '0.9rem', marginBottom: '10px' }}>Bundle: <span style={{ fontWeight: '700', color: 'var(--accent-gold)' }}>€{data.comparison.bundle_avg}</span></p>
                  
                  <div style={{ background: 'rgba(197, 160, 89, 0.2)', padding: '8px', borderRadius: '8px', border: '1px solid var(--accent-gold)' }}>
                    <p style={{ fontSize: '0.7rem', textTransform: 'uppercase', fontWeight: '800', color: 'var(--accent-gold)' }}>Recommended Strategy</p>
                    <p style={{ fontSize: '0.9rem', fontWeight: '700' }}>{data.comparison.recommendation}</p>
                    <p style={{ fontSize: '0.75rem', marginTop: '4px' }}>Potential gain: <span style={{ color: '#00cc66' }}>+{data.comparison.potential_gain_pct}%</span></p>
                  </div>
                </div>
              </div>
              
              <div style={{ display: 'flex', alignItems: 'start', gap: '8px', padding: '10px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                <Info size={16} color="var(--accent-gold)" style={{ flexShrink: 0, marginTop: '2px' }} />
                <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                  Historical data suggests {data.comparison.recommendation.toLowerCase().includes('bundling') ? 'bundle lots fetch higher unit prices' : 'selling individually maximizes total return'} for this specific vintage.
                </p>
              </div>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '2rem 0', color: 'var(--text-secondary)' }}>
              <AlertCircle size={32} style={{ marginBottom: '10px', opacity: 0.5 }} />
              <p style={{ fontSize: '0.8rem' }}>Insufficient data to benchmarking strategy comparison (lots vs single).</p>
            </div>
          )}
        </div>
      </div>

      {/* Main Analysis Tabs (Charts) */}
      <div className="glass-card" style={{ padding: '2rem', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <History size={20} /> Price Trend & Lot Composition
          </h3>
          <div className="glass-card" style={{ padding: '4px', borderRadius: '8px', display: 'flex', gap: '4px' }}>
              <button style={{ padding: '6px 12px', borderRadius: '6px', background: 'var(--accent-gold)', color: 'black', border: 'none', fontSize: '0.8rem', fontWeight: '700' }}>History</button>
              <button style={{ padding: '6px 12px', borderRadius: '6px', background: 'transparent', color: 'var(--text-secondary)', border: 'none', fontSize: '0.8rem' }}>Simulation</button>
          </div>
        </div>

        {hasHistory ? (
          <div style={{ height: '350px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.history} onClick={handlePointClick} style={{ cursor: 'pointer' }}>
                <defs>
                  <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--accent-gold)" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="var(--accent-gold)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                <XAxis 
                  dataKey="date" 
                  stroke="var(--text-secondary)" 
                  fontSize={11} 
                  tickFormatter={(val) => val.split(' ')[0]} 
                />
                <YAxis stroke="var(--text-secondary)" fontSize={11} tickFormatter={(val) => `€${val}`} />
                <Tooltip content={<CustomTooltip />} />
                <Area 
                  type="monotone" 
                  dataKey="price" 
                  stroke="var(--accent-gold)" 
                  fillOpacity={1} 
                  fill="url(#colorPrice)" 
                  strokeWidth={3} 
                  dot={{ 
                    r: 4, fill: 'var(--accent-gold)', strokeWidth: 2, stroke: '#000', cursor: 'pointer',
                    onClick: (props) => {
                      if (props && props.payload && props.payload.url) window.open(props.payload.url, '_blank');
                    }
                  }}
                  activeDot={{ 
                    r: 6, fill: 'white', cursor: 'pointer',
                    onClick: (props) => {
                      if (props && props.payload && props.payload.url) window.open(props.payload.url, '_blank');
                    }
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div style={{ height: '350px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', color: 'var(--text-secondary)' }}>
            <History size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
            <h4 style={{ marginBottom: '0.5rem' }}>No Historical Data Available</h4>
            <p style={{ textAlign: 'center', fontSize: '0.9rem' }}>
              There are no closed auction lots for this specific bottle combination.<br/>
              Price trends will appear once auction data becomes available.
            </p>
          </div>
        )}
      </div>

      {/* Nationality Analytics */}
      {data.nationalities && data.nationalities.length > 0 && (
        <div className="glass-card" style={{ padding: '2rem', marginBottom: '2rem' }}>
          <h3 style={{ fontSize: '1.2rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <MapPin size={20} color="var(--accent-gold)" />
            Global Demand Analytics
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
            
            {/* Volume Chart */}
            <div>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>LOTS WON BY NATIONALITY (VOLUME)</p>
              <div style={{ height: '300px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data.nationalities} layout="vertical" margin={{ left: 40, right: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={true} vertical={false} />
                    <XAxis type="number" stroke="var(--text-secondary)" fontSize={11} />
                    <YAxis dataKey="country" type="category" stroke="var(--text-secondary)" fontSize={11} width={80} />
                    <Tooltip 
                      contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}
                      formatter={(value) => [value, 'Lots Won']}
                    />
                    <Bar dataKey="lots_won" fill="rgba(197, 160, 89, 0.8)" radius={[0, 4, 4, 0]} barSize={20}>
                      {data.nationalities.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={index === 0 ? 'var(--accent-gold)' : 'rgba(197, 160, 89, 0.5)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Value Chart */}
            <div>
              <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem', fontWeight: '600' }}>AVERAGE PRICE PAID (VALUE)</p>
              <div style={{ height: '300px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={[...data.nationalities].sort((a,b) => b.avg_price - a.avg_price)} layout="horizontal" margin={{ top: 10, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                    <XAxis dataKey="country" stroke="var(--text-secondary)" fontSize={11} interval={0} angle={-45} textAnchor="end" height={60} />
                    <YAxis stroke="var(--text-secondary)" fontSize={11} tickFormatter={(val) => `€${val}`} />
                    <Tooltip 
                      contentStyle={{ background: 'rgba(0,0,0,0.8)', border: '1px solid var(--glass-border)', borderRadius: '8px' }}
                      formatter={(value) => [`€${value.toFixed(2)}`, 'Average Price']}
                    />
                    <Bar dataKey="avg_price" fill="#2ecc71" radius={[4, 4, 0, 0]} barSize={30}>
                       {[...data.nationalities].sort((a,b) => b.avg_price - a.avg_price).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={index === 0 ? '#2ecc71' : 'rgba(46, 204, 113, 0.5)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Extended History Log */}
      <div className="glass-card" style={{ padding: '0' }}>
        <div style={{ padding: '1.5rem', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ fontSize: '1.1rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <ShoppingBag size={18} /> Detailed Sales Experience
          </h3>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {hasHistory ? `Showing ${data.history.length} results` : 'No sales data available'}
          </span>
        </div>
        
        {hasHistory ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ margin: '0' }}>
              <thead>
                <tr>
                  <th>Closing Date</th>
                  <th>Composition</th>
                  <th>Total Price</th>
                  <th>Unit Price</th>
                  <th>Reserve</th>
                  <th>Result</th>
                  <th>Link</th>
                </tr>
              </thead>
              <tbody>
                {data.history.slice().reverse().map((entry, idx) => (
                  <tr key={idx} className="hover-row">
                    <td>{entry.date}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: entry.num_bottles > 1 ? 'var(--accent-gold)' : 'rgba(255,255,255,0.2)' }}></span>
                        {entry.num_bottles} btl(s)
                      </div>
                    </td>
                    <td style={{ fontWeight: '700' }}>€{entry.price.toFixed(2)}</td>
                    <td style={{ color: 'var(--text-secondary)' }}>€{entry.price_per_bottle.toFixed(2)} / btl</td>
                    <td>{entry.reserve === 'Y' ? <span style={{ color: 'var(--accent-gold)' }}>Yes</span> : 'No'}</td>
                    <td>
                      <span className={`status-badge ${entry.price > 0 ? 'status-open' : 'status-closed'}`}>
                        {entry.price > 0 ? 'MATCHED' : 'PASSED'}
                      </span>
                    </td>
                    <td>
                      <a href={entry.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-gold)' }}>
                        <ExternalLink size={16} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            <ShoppingBag size={48} style={{ marginBottom: '1rem', opacity: 0.3 }} />
            <h4 style={{ marginBottom: '0.5rem' }}>No Sales History</h4>
            <p style={{ fontSize: '0.9rem' }}>
              This bottle combination has not appeared in any closed auctions yet.<br/>
              Sales data will be displayed here once auctions are completed.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default BottleDetail;

import React, { useState, useEffect, useCallback } from 'react';
import CacheCluster3D from './components/CacheCluster3D.jsx';

const API_BASE = '';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [apiKey, setApiKey] = useState(localStorage.getItem('cache_api_key') || '');
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState(apiKey);
  const [show3DCluster, setShow3DCluster] = useState(true);

  // App telemetry & stats
  const [backendInfo, setBackendInfo] = useState({ backend: 'memory', status: 'healthy' });
  const [availableBackends, setAvailableBackends] = useState(['memory', 'redis', 'memcached']);
  const [stats, setStats] = useState({
    hits: 0,
    misses: 0,
    total_reads: 0,
    hit_ratio_percent: 0,
    sets: 0,
    deletes: 0,
    clears: 0,
    uptime_seconds: 0,
    backend_stats: {},
  });
  const [healthData, setHealthData] = useState(null);
  const [operationLogs, setOperationLogs] = useState([]);
  const [toast, setToast] = useState(null);

  // Single Operation form state
  const [opKey, setOpKey] = useState('');
  const [opValue, setOpValue] = useState('');
  const [opTtl, setOpTtl] = useState('');
  const [opResponse, setOpResponse] = useState(null);

  // Batch Operation form state
  const [batchItems, setBatchItems] = useState('{\n  "user:1": {"name": "Alice"},\n  "user:2": {"name": "Bob"}\n}');
  const [batchTtl, setBatchTtl] = useState('60');
  const [batchKeys, setBatchKeys] = useState('user:1, user:2');
  const [batchResponse, setBatchResponse] = useState(null);

  // Benchmark state
  const [benchmarkIterations, setBenchmarkIterations] = useState(50);
  const [benchmarking, setBenchmarking] = useState(false);
  const [benchmarkResults, setBenchmarkResults] = useState(null);

  const showToast = (message, type = 'info') => {
    setToast({ message, type, id: Date.now() });
    setTimeout(() => setToast(null), 4000);
  };

  const addLog = (action, target, status, durationMs, details = null) => {
    const entry = {
      id: Date.now() + Math.random(),
      time: new Date().toLocaleTimeString(),
      action,
      target,
      status,
      durationMs: durationMs ? `${durationMs.toFixed(2)}ms` : '-',
      details,
    };
    setOperationLogs((prev) => [entry, ...prev.slice(0, 49)]);
  };

  const getHeaders = useCallback(() => {
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }, [apiKey]);

  // Fetch telemetry
  const fetchDashboardData = useCallback(async () => {
    try {
      const bRes = await fetch(`${API_BASE}/backend`);
      if (bRes.ok) {
        const bData = await bRes.json();
        setBackendInfo(bData);
      }

      const avRes = await fetch(`${API_BASE}/backends`);
      if (avRes.ok) {
        const avData = await avRes.json();
        setAvailableBackends(avData.available || ['memory', 'redis', 'memcached']);
      }

      const hRes = await fetch(`${API_BASE}/health`);
      const hData = await hRes.json();
      setHealthData(hData);

      const sRes = await fetch(`${API_BASE}/stats`, { headers: getHeaders() });
      if (sRes.ok) {
        const sData = await sRes.json();
        setStats(sData);
      }
    } catch (err) {
      console.error('Error fetching dashboard telemetry:', err);
    }
  }, [getHeaders]);

  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 3000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  const handleSaveApiKey = () => {
    setApiKey(apiKeyInput.trim());
    localStorage.setItem('cache_api_key', apiKeyInput.trim());
    setShowApiKeyModal(false);
    showToast('API Key saved successfully', 'success');
  };

  const handleSwitchBackend = async (target) => {
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/backend/switch`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ backend: target }),
      });
      const data = await res.json();
      const dur = performance.now() - start;

      if (res.ok) {
        showToast(`Switched backend to ${target}`, 'success');
        addLog('SWITCH_BACKEND', target, 'SUCCESS', dur);
        fetchDashboardData();
      } else {
        showToast(`Switch failed: ${data.message || data.error}`, 'error');
        addLog('SWITCH_BACKEND', target, 'FAILED', dur, data.message);
      }
    } catch (err) {
      showToast(`Network error switching to ${target}`, 'error');
      addLog('SWITCH_BACKEND', target, 'ERROR', performance.now() - start, err.message);
    }
  };

  const handleClearCache = async () => {
    if (!window.confirm(`Are you sure you want to clear the entire ${backendInfo.backend} cache?`)) return;
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      const data = await res.json();
      const dur = performance.now() - start;

      if (res.ok) {
        showToast('Cache cleared successfully', 'success');
        addLog('CLEAR_CACHE', backendInfo.backend, 'SUCCESS', dur);
        fetchDashboardData();
      } else {
        showToast(`Clear failed: ${data.message || data.error}`, 'error');
        addLog('CLEAR_CACHE', backendInfo.backend, 'FAILED', dur, data.message);
      }
    } catch (err) {
      showToast('Error clearing cache', 'error');
    }
  };

  const handleSingleGet = async () => {
    if (!opKey.trim()) return showToast('Please enter a key', 'error');
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/${encodeURIComponent(opKey.trim())}`);
      const data = await res.json();
      const dur = performance.now() - start;
      setOpResponse({ status: res.status, data });
      addLog('GET', opKey, res.ok ? 'HIT' : 'MISS', dur);
      fetchDashboardData();
    } catch (err) {
      setOpResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleSingleSet = async () => {
    if (!opKey.trim()) return showToast('Please enter a key', 'error');
    let parsedVal = opValue;
    try {
      parsedVal = JSON.parse(opValue);
    } catch (e) {
      parsedVal = opValue;
    }

    const payload = { value: parsedVal };
    if (opTtl.trim()) {
      const ttlNum = parseInt(opTtl, 10);
      if (isNaN(ttlNum)) return showToast('TTL must be an integer', 'error');
      payload.ttl = ttlNum;
    }

    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/${encodeURIComponent(opKey.trim())}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setOpResponse({ status: res.status, data });
      addLog('SET', opKey, res.ok ? 'SUCCESS' : 'FAILED', dur);
      if (res.ok) showToast(`Key '${opKey}' stored successfully`, 'success');
      fetchDashboardData();
    } catch (err) {
      setOpResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleSingleDelete = async () => {
    if (!opKey.trim()) return showToast('Please enter a key', 'error');
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/${encodeURIComponent(opKey.trim())}`, {
        method: 'DELETE',
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setOpResponse({ status: res.status, data });
      addLog('DELETE', opKey, res.ok ? 'SUCCESS' : 'FAILED', dur);
      if (res.ok) showToast(`Key '${opKey}' deleted`, 'success');
      fetchDashboardData();
    } catch (err) {
      setOpResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleBatchSet = async () => {
    let itemsObj;
    try {
      itemsObj = JSON.parse(batchItems);
    } catch (err) {
      return showToast('Invalid JSON in Batch Items payload', 'error');
    }

    const payload = { items: itemsObj };
    if (batchTtl.trim()) {
      payload.ttl = parseInt(batchTtl, 10);
    }

    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/batch/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setBatchResponse({ status: res.status, data });
      addLog('BATCH_SET', `${Object.keys(itemsObj).length} keys`, res.ok ? 'SUCCESS' : 'FAILED', dur);
      if (res.ok) showToast(`Stored ${Object.keys(itemsObj).length} keys in batch`, 'success');
      fetchDashboardData();
    } catch (err) {
      setBatchResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleBatchGet = async () => {
    const keysArray = batchKeys.split(',').map((k) => k.trim()).filter(Boolean);
    if (!keysArray.length) return showToast('Please enter at least one key', 'error');

    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/batch/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keys: keysArray }),
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setBatchResponse({ status: res.status, data });
      addLog('BATCH_GET', `${keysArray.length} keys`, 'SUCCESS', dur);
      fetchDashboardData();
    } catch (err) {
      setBatchResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleBatchDelete = async () => {
    const keysArray = batchKeys.split(',').map((k) => k.trim()).filter(Boolean);
    if (!keysArray.length) return showToast('Please enter at least one key', 'error');

    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/cache/batch/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keys: keysArray }),
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setBatchResponse({ status: res.status, data });
      addLog('BATCH_DELETE', `${keysArray.length} keys`, res.ok ? 'SUCCESS' : 'FAILED', dur);
      if (res.ok) showToast(`Deleted ${keysArray.length} keys in batch`, 'success');
      fetchDashboardData();
    } catch (err) {
      setBatchResponse({ status: 500, data: { error: err.message } });
    }
  };

  const handleRunBenchmark = async () => {
    setBenchmarking(true);
    const start = performance.now();
    try {
      const res = await fetch(`${API_BASE}/benchmark/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ iterations: benchmarkIterations, backends: ['memory', 'redis', 'memcached'] }),
      });
      const data = await res.json();
      const dur = performance.now() - start;
      setBenchmarkResults(data);
      addLog('BENCHMARK', `${benchmarkIterations} ops`, 'COMPLETE', dur);
      showToast('Benchmark run completed', 'success');
    } catch (err) {
      showToast('Benchmark execution failed', 'error');
    } finally {
      setBenchmarking(false);
    }
  };

  const hitRatio = stats.hit_ratio_percent || 0;

  return (
    <div className="app-container" id="app-root">
      {/* 3D Toast notifications */}
      {toast && (
        <div className="toast-container" id="toast-container">
          <div className={`toast-3d ${toast.type}`} id="active-toast">
            <span>{toast.type === 'success' ? '✓' : toast.type === 'error' ? '✕' : 'ℹ'}</span>
            <span>{toast.message}</span>
          </div>
        </div>
      )}

      {/* 3D Futuristic Header */}
      <header className="app-header" id="app-header">
        <div className="brand-section">
          <div className="brand-logo-3d">U</div>
          <div>
            <h1 className="brand-title">Universal-Cache-Manager</h1>
            <p className="brand-subtitle">SIH P-003 &bull; Pluggable 3D Abstraction Layer</p>
          </div>
        </div>

        <div className="header-status-group">
          {/* Active Backend Indicator */}
          <div className="backend-indicator-3d" id="header-backend-indicator">
            <span style={{ opacity: 0.5 }}>ENGINE:</span>
            <span style={{ textTransform: 'uppercase' }}>{backendInfo.backend}</span>
          </div>

          {/* Health Badge */}
          <div className="status-badge-3d" id="header-health-badge">
            <span className={`status-dot ${backendInfo.status === 'healthy' ? 'healthy' : 'unhealthy'}`}></span>
            <span style={{ textTransform: 'capitalize' }}>{backendInfo.status}</span>
          </div>

          {/* 3D Viewport Toggle */}
          <button 
            className="btn-icon-3d"
            onClick={() => setShow3DCluster(!show3DCluster)}
            title="Toggle 3D Interactive View"
          >
            {show3DCluster ? '🌐 3D Core Active' : '💠 Show 3D'}
          </button>

          {/* API Key Modal Button */}
          <button 
            className="btn-icon-3d" 
            id="open-api-key-modal" 
            onClick={() => setShowApiKeyModal(true)}
          >
            🔑 {apiKey ? 'Key Configured' : 'Set API Key'}
          </button>
        </div>
      </header>

      {/* Nav Tabs */}
      <nav className="tabs-navigation" id="dashboard-navigation">
        <button 
          id="tab-overview" 
          className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          📊 Overview
        </button>
        <button 
          id="tab-operations" 
          className={`tab-btn ${activeTab === 'operations' ? 'active' : ''}`}
          onClick={() => setActiveTab('operations')}
        >
          ⚡ Cache Operations
        </button>
        <button 
          id="tab-management" 
          className={`tab-btn ${activeTab === 'management' ? 'active' : ''}`}
          onClick={() => setActiveTab('management')}
        >
          🔀 Backend Management
        </button>
        <button 
          id="tab-analytics" 
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          📈 Visual Analytics
        </button>
        <button 
          id="tab-benchmark" 
          className={`tab-btn ${activeTab === 'benchmark' ? 'active' : ''}`}
          onClick={() => setActiveTab('benchmark')}
        >
          🚀 Benchmark
        </button>
        <button 
          id="tab-health" 
          className={`tab-btn ${activeTab === 'health' ? 'active' : ''}`}
          onClick={() => setActiveTab('health')}
        >
          🩺 Health & Diagnostics
        </button>
        <button 
          id="tab-logs" 
          className={`tab-btn ${activeTab === 'logs' ? 'active' : ''}`}
          onClick={() => setActiveTab('logs')}
        >
          📜 Operation Logs ({operationLogs.length})
        </button>
      </nav>

      {/* Main Content */}
      <main className="main-content" id="main-content-viewport">
        
        {/* ====================================================
            TAB A: OVERVIEW
        ==================================================== */}
        {activeTab === 'overview' && (
          <div id="section-overview" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            
            {/* 3D Interactive Three.js Cluster Viewport */}
            {show3DCluster && (
              <CacheCluster3D 
                backend={backendInfo.backend} 
                health={backendInfo.status}
                stats={stats}
              />
            )}

            {/* Top Metric Cards */}
            <div className="grid-4">
              <div className="card-3d" id="card-hit-ratio">
                <div className="card-title">HIT RATIO</div>
                <div className="metric-value-3d" style={{ color: 'var(--accent-emerald)' }}>
                  {stats.hit_ratio_percent || 0}%
                </div>
                <div className="metric-subtitle">{stats.hits || 0} hits out of {stats.total_reads || 0} reads</div>
              </div>

              <div className="card-3d" id="card-total-reads">
                <div className="card-title">TOTAL READS</div>
                <div className="metric-value-3d" style={{ color: 'var(--accent-primary)' }}>
                  {stats.total_reads || 0}
                </div>
                <div className="metric-subtitle">{stats.misses || 0} cache misses</div>
              </div>

              <div className="card-3d" id="card-sets-count">
                <div className="card-title">TOTAL SETS</div>
                <div className="metric-value-3d" style={{ color: 'var(--accent-cyan)' }}>
                  {stats.sets || 0}
                </div>
                <div className="metric-subtitle">Key-value entries written</div>
              </div>

              <div className="card-3d" id="card-deletes-count">
                <div className="card-title">TOTAL DELETES</div>
                <div className="metric-value-3d" style={{ color: 'var(--accent-amber)' }}>
                  {stats.deletes || 0}
                </div>
                <div className="metric-subtitle">{stats.clears || 0} full cache clears</div>
              </div>
            </div>

            {/* Active Provider Banner & Quick Actions */}
            <div className="grid-2">
              <div className="card-3d" id="card-active-backend-overview">
                <div className="card-title">
                  <span>ACTIVE CACHE ENGINE</span>
                  <span className={`status-badge-3d ${backendInfo.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
                    {backendInfo.status}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px', marginTop: '12px' }}>
                  <div style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: 'var(--radius-md)',
                    background: 'rgba(99, 102, 241, 0.12)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '28px',
                    boxShadow: '0 8px 20px rgba(0, 0, 0, 0.4)'
                  }}>
                    {backendInfo.backend === 'redis' ? '🔴' : backendInfo.backend === 'memcached' ? '⚡' : '💾'}
                  </div>
                  <div>
                    <h2 style={{ fontSize: '22px', fontWeight: 800, textTransform: 'capitalize' }}>
                      {backendInfo.backend} Provider
                    </h2>
                    <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginTop: '2px' }}>
                      Uptime: {stats.uptime_seconds || 0}s &bull; Namespace: {stats.namespace || 'None'}
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px', marginTop: '24px', flexWrap: 'wrap' }}>
                  <button className="btn-3d btn-3d-primary" id="overview-btn-ops" onClick={() => setActiveTab('operations')}>
                    ⚡ Perform Cache Operations
                  </button>
                  <button className="btn-3d btn-3d-secondary" id="overview-btn-switch" onClick={() => setActiveTab('management')}>
                    🔀 Switch Backend
                  </button>
                  <button className="btn-3d btn-3d-danger" id="overview-btn-clear" onClick={handleClearCache}>
                    🗑️ Clear Store
                  </button>
                </div>
              </div>

              {/* Visual Performance Gauge */}
              <div className="card-3d" id="card-efficiency-gauge">
                <div className="card-title">CACHE EFFICIENCY & READ PERFORMANCE</div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '16px 0' }}>
                  <svg width="150" height="150" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="42" stroke="rgba(255,255,255,0.05)" strokeWidth="10" fill="none" />
                    <circle 
                      cx="50" 
                      cy="50" 
                      r="42" 
                      stroke="var(--accent-primary)" 
                      strokeWidth="10" 
                      fill="none" 
                      strokeDasharray="264"
                      strokeDashoffset={264 - (264 * hitRatio) / 100}
                      strokeLinecap="round"
                      transform="rotate(-90 50 50)"
                    />
                    <text x="50" y="55" textAnchor="middle" fill="#fff" fontSize="18" fontWeight="800" fontFamily="var(--font-mono)">
                      {hitRatio}%
                    </text>
                  </svg>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
                    Hit Ratio: {hitRatio}% &bull; Reads: {stats.total_reads || 0}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            TAB B: CACHE OPERATIONS
        ==================================================== */}
        {activeTab === 'operations' && (
          <div id="section-operations" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card-3d" id="card-single-operations">
              <div className="card-title">SINGLE KEY CACHE OPERATIONS</div>
              <div className="grid-3">
                <div className="form-group">
                  <label className="form-label" htmlFor="input-op-key">Key Name</label>
                  <input 
                    id="input-op-key"
                    className="input-control-3d" 
                    placeholder="e.g. user:profile:100" 
                    value={opKey}
                    onChange={(e) => setOpKey(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="input-op-value">Value (Text or JSON)</label>
                  <input 
                    id="input-op-value"
                    className="input-control-3d" 
                    placeholder='e.g. {"name": "Rahul", "role": "admin"}' 
                    value={opValue}
                    onChange={(e) => setOpValue(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="input-op-ttl">Optional TTL (Seconds)</label>
                  <input 
                    id="input-op-ttl"
                    type="number"
                    className="input-control-3d" 
                    placeholder="e.g. 60 (leave empty for persistent)" 
                    value={opTtl}
                    onChange={(e) => setOpTtl(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
                <button className="btn-3d btn-3d-primary" id="btn-op-get" onClick={handleSingleGet}>
                  🔍 GET
                </button>
                <button className="btn-3d btn-3d-primary" id="btn-op-set" onClick={handleSingleSet} style={{ background: 'linear-gradient(180deg, var(--accent-cyan), #0284c7)' }}>
                  💾 SET (with TTL)
                </button>
                <button className="btn-3d btn-3d-danger" id="btn-op-delete" onClick={handleSingleDelete}>
                  🗑️ DELETE
                </button>
              </div>

              {opResponse && (
                <div style={{ marginTop: '20px' }}>
                  <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '6px', letterSpacing: '0.05em' }}>
                    RESPONSE (Status: {opResponse.status})
                  </div>
                  <pre className="json-viewer-3d" id="single-op-response-viewer">
                    {JSON.stringify(opResponse.data, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Batch Operations */}
            <div className="card-3d" id="card-batch-operations">
              <div className="card-title">BATCH OPERATIONS (MGET / MSET / MDELETE)</div>
              <div className="grid-2">
                <div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="input-batch-items">Batch SET Items (JSON Object)</label>
                    <textarea 
                      id="input-batch-items"
                      className="input-control-3d"
                      value={batchItems}
                      onChange={(e) => setBatchItems(e.target.value)}
                      rows={5}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="input-batch-ttl">Batch TTL (Seconds)</label>
                    <input 
                      id="input-batch-ttl"
                      type="number"
                      className="input-control-3d"
                      value={batchTtl}
                      onChange={(e) => setBatchTtl(e.target.value)}
                    />
                  </div>
                  <button className="btn-3d btn-3d-primary" id="btn-batch-set" onClick={handleBatchSet}>
                    📦 Execute Batch SET
                  </button>
                </div>

                <div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="input-batch-keys">Batch Keys (Comma-separated)</label>
                    <input 
                      id="input-batch-keys"
                      className="input-control-3d"
                      value={batchKeys}
                      onChange={(e) => setBatchKeys(e.target.value)}
                    />
                  </div>
                  <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                    <button className="btn-3d btn-3d-primary" id="btn-batch-get" onClick={handleBatchGet}>
                      📥 Batch GET
                    </button>
                    <button className="btn-3d btn-3d-danger" id="btn-batch-delete" onClick={handleBatchDelete}>
                      🗑️ Batch DELETE
                    </button>
                  </div>

                  {batchResponse && (
                    <div style={{ marginTop: '20px' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '6px', letterSpacing: '0.05em' }}>
                        BATCH RESPONSE (Status: {batchResponse.status})
                      </div>
                      <pre className="json-viewer-3d" id="batch-op-response-viewer">
                        {JSON.stringify(batchResponse.data, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            TAB C: BACKEND MANAGEMENT
        ==================================================== */}
        {activeTab === 'management' && (
          <div id="section-management" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card-3d" id="card-backend-switcher">
              <div className="card-title">RUNTIME BACKEND SWITCHER</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '20px' }}>
                Hot-swap cache engines seamlessly without downtime. Pre-flight health checks verify candidate readiness before switching.
              </p>

              <div className="grid-3">
                {/* Memory Card */}
                <div className="card-3d" style={{ 
                  borderColor: backendInfo.backend === 'memory' ? 'var(--accent-emerald)' : 'var(--border-hairline)',
                  background: backendInfo.backend === 'memory' ? 'rgba(16, 185, 129, 0.08)' : 'var(--bg-card)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 800 }}>Memory</h3>
                    {backendInfo.backend === 'memory' && (
                      <span className="status-badge-3d" style={{ background: 'rgba(16,185,129,0.2)', color: '#6ee7b7' }}>ACTIVE</span>
                    )}
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '10px 0 16px' }}>
                    In-process thread-safe RLock, TTL expiration, and LRU capacity eviction. Zero network overhead.
                  </p>
                  <button 
                    id="switch-to-memory"
                    className="btn-3d btn-3d-secondary" 
                    style={{ width: '100%' }}
                    disabled={backendInfo.backend === 'memory'}
                    onClick={() => handleSwitchBackend('memory')}
                  >
                    {backendInfo.backend === 'memory' ? 'Currently Active' : 'Switch to Memory'}
                  </button>
                </div>

                {/* Redis Card */}
                <div className="card-3d" style={{ 
                  borderColor: backendInfo.backend === 'redis' ? 'var(--accent-rose)' : 'var(--border-hairline)',
                  background: backendInfo.backend === 'redis' ? 'rgba(244, 63, 94, 0.08)' : 'var(--bg-card)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 800 }}>Redis</h3>
                    {backendInfo.backend === 'redis' && (
                      <span className="status-badge-3d" style={{ background: 'rgba(244,63,94,0.2)', color: '#fda4af' }}>ACTIVE</span>
                    )}
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '10px 0 16px' }}>
                    Distributed in-memory store with native TTL expiration, connection pooling, and multi-key pipelines.
                  </p>
                  <button 
                    id="switch-to-redis"
                    className="btn-3d btn-3d-secondary" 
                    style={{ width: '100%' }}
                    disabled={backendInfo.backend === 'redis'}
                    onClick={() => handleSwitchBackend('redis')}
                  >
                    {backendInfo.backend === 'redis' ? 'Currently Active' : 'Switch to Redis'}
                  </button>
                </div>

                {/* Memcached Card */}
                <div className="card-3d" style={{ 
                  borderColor: backendInfo.backend === 'memcached' ? 'var(--accent-cyan)' : 'var(--border-hairline)',
                  background: backendInfo.backend === 'memcached' ? 'rgba(6, 182, 212, 0.08)' : 'var(--bg-card)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ fontSize: '18px', fontWeight: 800 }}>Memcached</h3>
                    {backendInfo.backend === 'memcached' && (
                      <span className="status-badge-3d" style={{ background: 'rgba(6,182,212,0.2)', color: '#67e8f9' }}>ACTIVE</span>
                    )}
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '10px 0 16px' }}>
                    High-performance binary key-value object cache with native TTL and pooled connections.
                  </p>
                  <button 
                    id="switch-to-memcached"
                    className="btn-3d btn-3d-secondary" 
                    style={{ width: '100%' }}
                    disabled={backendInfo.backend === 'memcached'}
                    onClick={() => handleSwitchBackend('memcached')}
                  >
                    {backendInfo.backend === 'memcached' ? 'Currently Active' : 'Switch to Memcached'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            TAB D: VISUAL ANALYTICS
        ==================================================== */}
        {activeTab === 'analytics' && (
          <div id="section-analytics" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="grid-2">
              {/* Hit vs Miss Chart */}
              <div className="card-3d" id="card-chart-hit-miss">
                <div className="card-title">HIT VS MISS DISTRIBUTION</div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-around', padding: '24px 0' }}>
                  <svg width="180" height="180" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="40" stroke="rgba(244, 63, 94, 0.2)" strokeWidth="16" fill="none" />
                    <circle 
                      cx="50" 
                      cy="50" 
                      r="40" 
                      stroke="var(--accent-emerald)" 
                      strokeWidth="16" 
                      fill="none" 
                      strokeDasharray="251"
                      strokeDashoffset={251 - (251 * (stats.hits || 0)) / Math.max(1, (stats.total_reads || 1))}
                      strokeLinecap="round"
                      transform="rotate(-90 50 50)"
                    />
                    <text x="50" y="55" textAnchor="middle" fill="#fff" fontSize="16" fontWeight="700">
                      {hitRatio}%
                    </text>
                  </svg>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'var(--accent-emerald)' }}></span>
                      <span style={{ fontSize: '13px' }}>Hits: <strong>{stats.hits || 0}</strong></span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'var(--accent-rose)' }}></span>
                      <span style={{ fontSize: '13px' }}>Misses: <strong>{stats.misses || 0}</strong></span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'var(--accent-primary)' }}></span>
                      <span style={{ fontSize: '13px' }}>Total Reads: <strong>{stats.total_reads || 0}</strong></span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Operations Breakdown Bar Chart */}
              <div className="card-3d" id="card-chart-ops">
                <div className="card-title">OPERATIONS BREAKDOWN</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '16px 0' }}>
                  {(() => {
                    const maxCount = Math.max(stats.total_reads, stats.sets, stats.deletes, stats.clears, 1);
                    return (
                      <>
                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                            <span>Reads ({stats.total_reads})</span>
                            <span>{Math.round((stats.total_reads / maxCount) * 100)}%</span>
                          </div>
                          <div style={{ height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${(stats.total_reads / maxCount) * 100}%`, background: 'var(--accent-primary)' }}></div>
                          </div>
                        </div>

                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                            <span>Sets ({stats.sets})</span>
                            <span>{Math.round((stats.sets / maxCount) * 100)}%</span>
                          </div>
                          <div style={{ height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${(stats.sets / maxCount) * 100}%`, background: 'var(--accent-cyan)' }}></div>
                          </div>
                        </div>

                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                            <span>Deletes ({stats.deletes})</span>
                            <span>{Math.round((stats.deletes / maxCount) * 100)}%</span>
                          </div>
                          <div style={{ height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${(stats.deletes / maxCount) * 100}%`, background: 'var(--accent-amber)' }}></div>
                          </div>
                        </div>

                        <div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                            <span>Clears ({stats.clears})</span>
                            <span>{Math.round((stats.clears / maxCount) * 100)}%</span>
                          </div>
                          <div style={{ height: '8px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${(stats.clears / maxCount) * 100}%`, background: 'var(--accent-rose)' }}></div>
                          </div>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            TAB E: BENCHMARK
        ==================================================== */}
        {activeTab === 'benchmark' && (
          <div id="section-benchmark" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card-3d" id="card-benchmark-runner">
              <div className="card-title">LIVE MULTI-BACKEND PERFORMANCE BENCHMARK</div>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '20px' }}>
                Executes real, un-simulated SET, GET, and DELETE workload loops against all backends to measure latency (ms) and throughput (ops/sec). Unavailable backends are explicitly flagged.
              </p>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <label htmlFor="benchmark-iterations-select" style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Iterations per stage:</label>
                  <select 
                    id="benchmark-iterations-select"
                    className="input-control-3d" 
                    style={{ width: '120px' }}
                    value={benchmarkIterations}
                    onChange={(e) => setBenchmarkIterations(Number(e.target.value))}
                    disabled={benchmarking}
                  >
                    <option value={25}>25 ops</option>
                    <option value={50}>50 ops</option>
                    <option value={100}>100 ops</option>
                    <option value={250}>250 ops</option>
                  </select>
                </div>

                <button 
                  id="btn-start-benchmark"
                  className="btn-3d btn-3d-primary" 
                  onClick={handleRunBenchmark}
                  disabled={benchmarking}
                >
                  {benchmarking ? '⏳ Running Workload Benchmark...' : '🚀 Execute Real Benchmark'}
                </button>
              </div>

              {/* Benchmark Results Table */}
              {benchmarkResults && (
                <div>
                  <div className="table-container">
                    <table className="custom-table-3d" id="benchmark-results-table">
                      <thead>
                        <tr>
                          <th>Backend</th>
                          <th>Status</th>
                          <th>SET Avg (ms)</th>
                          <th>GET Avg (ms)</th>
                          <th>DELETE Avg (ms)</th>
                          <th>Throughput (ops/sec)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(benchmarkResults.results).map(([backendKey, data]) => (
                          <tr key={backendKey}>
                            <td style={{ fontWeight: 700, textTransform: 'capitalize' }}>
                              {backendKey}
                            </td>
                            <td>
                              {data.available ? (
                                <span className="status-badge-3d" style={{ color: 'var(--accent-emerald)', background: 'rgba(16,185,129,0.1)' }}>
                                  ✓ Available
                                </span>
                              ) : (
                                <span className="status-badge-3d" style={{ color: 'var(--accent-rose)', background: 'rgba(244,63,94,0.1)' }}>
                                  ✕ Unavailable ({data.reason || 'Offline'})
                                </span>
                              )}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>
                              {data.set_avg_ms !== null ? `${data.set_avg_ms} ms` : '-'}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>
                              {data.get_avg_ms !== null ? `${data.get_avg_ms} ms` : '-'}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>
                              {data.delete_avg_ms !== null ? `${data.delete_avg_ms} ms` : '-'}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: data.throughput_ops_sec ? 'var(--accent-cyan)' : 'inherit' }}>
                              {data.throughput_ops_sec !== null ? `${data.throughput_ops_sec.toLocaleString()} ops/s` : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ====================================================
            TAB F: HEALTH & DIAGNOSTICS
        ==================================================== */}
        {activeTab === 'health' && (
          <div id="section-health" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card-3d" id="card-diagnostics">
              <div className="card-title">
                <span>ACTIVE BACKEND DIAGNOSTICS</span>
                <span className="status-badge-3d" style={{ color: 'var(--accent-emerald)', background: 'rgba(16,185,129,0.1)' }}>
                  🔒 Zero Secrets Exposed
                </span>
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '20px' }}>
                Normalized diagnostic inspection verifying latency, server parameters, and connection details with passwords safely sanitized.
              </p>

              <pre className="json-viewer-3d" id="health-diagnostics-viewer">
                {JSON.stringify(healthData || { status: 'loading...' }, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {/* ====================================================
            TAB G: OPERATION LOGS
        ==================================================== */}
        {activeTab === 'logs' && (
          <div id="section-logs" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div className="card-3d" id="card-operation-logs">
              <div className="card-title">
                <span>RECENT OPERATION AUDIT TRAIL</span>
                <button className="btn-3d btn-3d-secondary" style={{ padding: '4px 10px', fontSize: '11px' }} onClick={() => setOperationLogs([])}>
                  Clear Log View
                </button>
              </div>

              {operationLogs.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '13px', padding: '16px 0' }}>
                  No operations recorded in this browser session yet. Perform cache reads, writes, or benchmark runs to view live logs.
                </p>
              ) : (
                <div className="table-container">
                  <table className="custom-table-3d" id="audit-logs-table">
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Action</th>
                        <th>Target</th>
                        <th>Status</th>
                        <th>Latency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {operationLogs.map((log) => (
                        <tr key={log.id}>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{log.time}</td>
                          <td style={{ fontWeight: 700 }}>{log.action}</td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{log.target}</td>
                          <td>
                            <span className="status-badge-3d" style={{
                              color: log.status.includes('SUCCESS') || log.status.includes('HIT') || log.status.includes('COMPLETE') 
                                ? 'var(--accent-emerald)' 
                                : 'var(--accent-rose)',
                              background: 'rgba(255,255,255,0.04)'
                            }}>
                              {log.status}
                            </span>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{log.durationMs}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

      </main>

      {/* 3D API Key Modal */}
      {showApiKeyModal && (
        <div className="modal-overlay" id="api-key-modal">
          <div className="modal-content-3d">
            <h3 style={{ fontSize: '18px', fontWeight: 800, marginBottom: '8px' }}>Administrative API Key</h3>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '16px' }}>
              Enter the configured <code style={{ color: 'var(--accent-cyan)' }}>CACHE_API_KEY</code> to authenticate administrative actions (backend switching, cache clearing, and stats).
            </p>

            <div className="form-group">
              <label className="form-label" htmlFor="input-modal-api-key">API Key</label>
              <input 
                id="input-modal-api-key"
                type="password"
                className="input-control-3d" 
                placeholder="Enter secret API key" 
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' }}>
              <button className="btn-3d btn-3d-secondary" onClick={() => setShowApiKeyModal(false)}>
                Cancel
              </button>
              <button className="btn-3d btn-3d-primary" id="btn-save-api-key" onClick={handleSaveApiKey}>
                Save Key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

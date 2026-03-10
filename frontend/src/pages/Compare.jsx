import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getAggregates } from '../api'

const MATURITY_ORDER = ['theoretical', 'lab_scale', 'pilot', 'commercial']

export default function Compare() {
  const [agg, setAgg] = useState(null)
  const [sectors, setSectors] = useState([])
  const [sectorA, setSectorA] = useState('')
  const [sectorB, setSectorB] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getAggregates({ top: 200 })
      .then((d) => {
        setAgg(d)
        setSectors((d.top_sectors || []).map((s) => s.sector))
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading</p>
  if (!agg) return null

  const bySector = agg.by_sector || {}
  const bySectorMaturity = agg.by_sector_maturity || {}
  const bySectorSentiment = agg.by_sector_sentiment || {}

  const countA = sectorA ? (bySector[sectorA] ?? 0) : 0
  const countB = sectorB ? (bySector[sectorB] ?? 0) : 0
  const matA = sectorA ? (bySectorMaturity[sectorA] || {}) : {}
  const matB = sectorB ? (bySectorMaturity[sectorB] || {}) : {}
  const sentA = sectorA ? (bySectorSentiment[sectorA] || {}) : {}
  const sentB = sectorB ? (bySectorSentiment[sectorB] || {}) : {}

  return (
    <section>
      <h2>Compare sectors</h2>
      <p className="meta">Side-by-side volume, maturity mix, and sentiment for two sectors.</p>

      <div style={{ display: 'flex', gap: '2rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        <div>
          <label htmlFor="compare-a" className="meta">Sector A: </label>
          <select
            id="compare-a"
            value={sectorA}
            onChange={(e) => setSectorA(e.target.value)}
            style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem', minWidth: '180px' }}
          >
            <option value="">Select…</option>
            {sectors.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="compare-b" className="meta">Sector B: </label>
          <select
            id="compare-b"
            value={sectorB}
            onChange={(e) => setSectorB(e.target.value)}
            style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem', minWidth: '180px' }}
          >
            <option value="">Select…</option>
            {sectors.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="compare-grid">
        <div className="dashboard-card">
          <h3>{sectorA || 'Sector A'}</h3>
          {sectorA ? (
            <>
              <p><strong>{countA}</strong> technology mentions</p>
              <h4 style={{ fontSize: '0.8125rem', marginTop: '0.75rem' }}>Maturity</h4>
              <ul className="segment-list">
                {MATURITY_ORDER.map((m) => (
                  <li key={m}><span>{m}</span><span>{matA[m] ?? 0}</span></li>
                ))}
              </ul>
              <h4 style={{ fontSize: '0.8125rem', marginTop: '0.75rem' }}>Sentiment (extractions)</h4>
              <ul className="segment-list">
                {Object.entries(sentA).map(([k, v]) => (
                  <li key={k}><span>{k}</span><span>{v}</span></li>
                ))}
              </ul>
              <Link to={`/explore/sector/${encodeURIComponent(sectorA)}`}>View extractions →</Link>
            </>
          ) : (
            <p className="meta">Select a sector.</p>
          )}
        </div>
        <div className="dashboard-card">
          <h3>{sectorB || 'Sector B'}</h3>
          {sectorB ? (
            <>
              <p><strong>{countB}</strong> technology mentions</p>
              <h4 style={{ fontSize: '0.8125rem', marginTop: '0.75rem' }}>Maturity</h4>
              <ul className="segment-list">
                {MATURITY_ORDER.map((m) => (
                  <li key={m}><span>{m}</span><span>{matB[m] ?? 0}</span></li>
                ))}
              </ul>
              <h4 style={{ fontSize: '0.8125rem', marginTop: '0.75rem' }}>Sentiment (extractions)</h4>
              <ul className="segment-list">
                {Object.entries(sentB).map(([k, v]) => (
                  <li key={k}><span>{k}</span><span>{v}</span></li>
                ))}
              </ul>
              <Link to={`/explore/sector/${encodeURIComponent(sectorB)}`}>View extractions →</Link>
            </>
          ) : (
            <p className="meta">Select a sector.</p>
          )}
        </div>
      </div>

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

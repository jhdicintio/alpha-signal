import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getAggregates } from '../api'

const MATURITY_ORDER = ['theoretical', 'lab_scale', 'pilot', 'commercial']
const MATURITY_LABELS = { theoretical: 'Theoretical', lab_scale: 'Lab scale', pilot: 'Pilot', commercial: 'Commercial' }

export default function Landscape() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getAggregates({ top: 100 })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading landscape</p>
  if (!data) return null

  const sectors = data.top_sectors || []
  const maxCount = Math.max(...sectors.map((s) => s.count), 1)

  return (
    <section>
      <h2>Sector & technology landscape</h2>
      <p className="meta">Where research attention is focused. Click a sector to drill down.</p>

      <div className="chart-section">
        <h3>Extractions by sector</h3>
        <ul className="list bar-list">
          {sectors.map(({ sector, count }) => (
            <li key={sector} className="bar-row">
              <Link to={`/explore/sector/${encodeURIComponent(sector)}`} className="bar-label">
                {sector}
              </Link>
              <span className="bar-wrap">
                <span className="bar" style={{ width: `${(count / maxCount) * 100}%` }} />
              </span>
              <span className="bar-value">{count}</span>
            </li>
          ))}
        </ul>
      </div>

      {sectors.length > 0 && (
        <div className="chart-section">
          <h3>Maturity mix by sector</h3>
          <p className="meta">Technology mentions by maturity stage (theoretical → commercial).</p>
          <div className="maturity-grid">
            {sectors.slice(0, 15).map(({ sector }) => {
              const mat = data.by_sector_maturity?.[sector] || {}
              const total = MATURITY_ORDER.reduce((s, m) => s + (mat[m] || 0), 0)
              if (total === 0) return null
              return (
                <div key={sector} className="maturity-card">
                  <Link to={`/explore/sector/${encodeURIComponent(sector)}`} className="maturity-sector">
                    {sector}
                  </Link>
                  <div className="maturity-stack">
                    {MATURITY_ORDER.map((m) => {
                      const v = mat[m] || 0
                      const pct = total ? (v / total) * 100 : 0
                      return (
                        <span
                          key={m}
                          className="maturity-seg"
                          style={{ width: `${pct}%` }}
                          title={`${MATURITY_LABELS[m]}: ${v}`}
                        />
                      )
                    })}
                  </div>
                  <span className="maturity-total">{total}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

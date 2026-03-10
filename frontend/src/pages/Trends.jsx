import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getTrends, getAggregates } from '../api'

export default function Trends() {
  const [points, setPoints] = useState([])
  const [sectors, setSectors] = useState([])
  const [sector, setSector] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getTrends({ sector: sector || undefined })
      .then((d) => setPoints(d.points || []))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [sector])

  useEffect(() => {
    getAggregates({ top: 100 })
      .then((d) => setSectors((d.top_sectors || []).map((s) => s.sector)))
      .catch(() => {})
  }, [])

  if (error) return <p className="error">Error: {error}</p>
  if (loading && points.length === 0) return <p className="loading">Loading trends</p>

  const maxCount = Math.max(...points.map((p) => p.count), 1)

  return (
    <section>
      <h2>Trends over time</h2>
      <p className="meta">Extraction count by publication month. Filter by sector to see where activity is heating up.</p>

      <div style={{ marginBottom: '1rem' }}>
        <label htmlFor="trends-sector" className="meta">Sector: </label>
        <select
          id="trends-sector"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem' }}
        >
          <option value="">All</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {points.length === 0 ? (
        <p className="meta">No data for this selection. Ensure articles have publication dates.</p>
      ) : (
        <>
          <div className="trends-chart">
            {points.map((p) => (
              <span
                key={p.period}
                className="trends-bar"
                style={{ height: `${(p.count / maxCount) * 100}%` }}
                title={`${p.period}: ${p.count}`}
              />
            ))}
          </div>
          <div className="trends-labels">
            {points.length > 0 && (
              <>
                <span>{points[0].period}</span>
                <span>{points[points.length - 1].period}</span>
              </>
            )}
          </div>
        </>
      )}

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getAggregates, getExtractions } from '../api'

const MATURITY_ORDER = ['theoretical', 'lab_scale', 'pilot', 'commercial']
const MATURITY_LABELS = { theoretical: 'Theoretical', lab_scale: 'Lab scale', pilot: 'Pilot', commercial: 'Commercial' }

export default function MaturityPipeline() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sectorFilter, setSectorFilter] = useState('')
  const [clickedMaturity, setClickedMaturity] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getAggregates(sectorFilter ? { sector: sectorFilter } : {})
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [sectorFilter])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading pipeline</p>
  if (!data) return null

  const byMat = data.by_maturity || {}
  const totals = MATURITY_ORDER.map((m) => byMat[m] || 0)
  const maxVal = Math.max(...totals, 1)

  return (
    <section>
      <h2>Maturity pipeline</h2>
      <p className="meta">Technology mentions by stage (theoretical → commercial). Click a stage to see extractions.</p>

      <div style={{ marginBottom: '1rem' }}>
        <label htmlFor="sector-filter" className="meta">Filter by sector: </label>
        <input
          id="sector-filter"
          type="text"
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
          placeholder="e.g. Energy Storage"
          style={{ marginLeft: '0.5rem', padding: '0.25rem 0.5rem', width: '200px' }}
        />
      </div>

      <div className="chart-section">
        <h3>Count by maturity</h3>
        <ul className="list bar-list">
          {MATURITY_ORDER.map((m) => (
            <li key={m} className="bar-row">
              <button
                type="button"
                className="bar-label"
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left', padding: 0,
                  color: 'var(--db-accent)', font: 'inherit',
                }}
                onClick={() => setClickedMaturity(m)}
              >
                {MATURITY_LABELS[m]}
              </button>
              <span className="bar-wrap">
                <span className="bar" style={{ width: `${((byMat[m] || 0) / maxVal) * 100}%` }} />
              </span>
              <span className="bar-value">{byMat[m] || 0}</span>
            </li>
          ))}
        </ul>
      </div>

      {clickedMaturity && (
        <div className="chart-section" style={{ marginTop: '1.5rem' }}>
          <h3>Extractions with at least one &quot;{MATURITY_LABELS[clickedMaturity]}&quot; technology</h3>
          <ExtractionsByMaturity maturity={clickedMaturity} sector={sectorFilter || undefined} />
        </div>
      )}

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

function ExtractionsByMaturity({ maturity, sector }) {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    getExtractions({ maturity, sector, limit: 15 })
      .then(setData)
      .finally(() => setLoading(false))
  }, [maturity, sector])
  if (loading) return <p className="loading">Loading…</p>
  if (data.items.length === 0) return <p className="meta">None found.</p>
  return (
    <>
      <p className="meta">Total: {data.total}. Showing up to 15.</p>
      <ul className="list">
        {data.items.map((item) => (
          <li key={`${item.article.source}-${item.article.source_id}`}>
            <Link to={`/extractions/${encodeURIComponent(item.article.source)}/${encodeURIComponent(item.article.source_id)}`}>
              {item.article.title || item.article.source_id}
            </Link>
            <span className="source">{item.article.source}</span>
            {item.extraction?.summary && <p className="summary">{item.extraction.summary}</p>}
          </li>
        ))}
      </ul>
      <Link to={`/extractions?maturity=${encodeURIComponent(maturity)}${sector ? `&sector=${encodeURIComponent(sector)}` : ''}`}>
        View all →
      </Link>
    </>
  )
}

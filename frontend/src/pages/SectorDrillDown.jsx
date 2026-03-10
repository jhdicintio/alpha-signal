import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getExtractions, getAggregates } from '../api'

const MATURITY_ORDER = ['theoretical', 'lab_scale', 'pilot', 'commercial']

export default function SectorDrillDown() {
  const { sector } = useParams()
  const [list, setList] = useState({ items: [], total: 0, limit: 20, offset: 0 })
  const [agg, setAgg] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const limit = 20

  useEffect(() => {
    if (!sector) return
    setLoading(true)
    setError(null)
    Promise.all([
      getExtractions({ sector, limit, offset: page * limit, sort: 'publication_date', order: 'desc' }),
      getAggregates({ sector }),
    ])
      .then(([listData, aggData]) => {
        setList(listData)
        setAgg(aggData)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [sector, page])

  if (error) return <p className="error">Error: {error}</p>
  if (loading && !list.items?.length) return <p className="loading">Loading sector</p>
  if (!sector) return null

  const totalPages = Math.ceil((list.total || 0) / limit)
  const mat = agg?.by_sector_maturity?.[sector] || {}
  const sent = agg?.by_sector_sentiment?.[sector] || {}

  return (
    <section>
      <h2>{decodeURIComponent(sector)}</h2>
      <p className="meta">All extractions that mention this sector. Total: {list.total ?? 0}</p>

      {(Object.keys(mat).length > 0 || Object.keys(sent).length > 0) && (
        <div className="dashboard-grid" style={{ marginBottom: '1.5rem' }}>
          {Object.keys(mat).length > 0 && (
            <div className="dashboard-card">
              <h3>Maturity (tech mentions)</h3>
              <ul className="segment-list">
                {MATURITY_ORDER.filter((m) => mat[m]).map((m) => (
                  <li key={m}><span>{m}</span><span>{mat[m]}</span></li>
                ))}
              </ul>
            </div>
          )}
          {Object.keys(sent).length > 0 && (
            <div className="dashboard-card">
              <h3>Sentiment (extractions)</h3>
              <ul className="segment-list">
                {Object.entries(sent).map(([k, v]) => (
                  <li key={k}><span>{k}</span><span>{v}</span></li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <h3>Extractions</h3>
      <ul className="list">
        {(list.items || []).map((item) => (
          <li key={`${item.article.source}-${item.article.source_id}`}>
            <Link to={`/extractions/${encodeURIComponent(item.article.source)}/${encodeURIComponent(item.article.source_id)}`}>
              {item.article.title || item.article.source_id}
            </Link>
            <span className="source">{item.article.source}</span>
            {item.article.publication_date && (
              <span className="meta" style={{ marginLeft: '0.5rem' }}>{item.article.publication_date}</span>
            )}
            {item.extraction?.summary && <p className="summary">{item.extraction.summary}</p>}
          </li>
        ))}
      </ul>
      {totalPages > 1 && (
        <nav className="pagination">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span>Page {page + 1} of {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>Next</button>
        </nav>
      )}

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore/landscape">← Sector landscape</Link> · <Link to="/explore">Explore</Link>
      </p>
    </section>
  )
}

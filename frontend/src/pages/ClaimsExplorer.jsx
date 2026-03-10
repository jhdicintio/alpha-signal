import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getExtractions } from '../api'

export default function ClaimsExplorer() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const limit = 20

  useEffect(() => {
    setLoading(true)
    setError(null)
    getExtractions({ quantitative_claims: true, limit, offset: page * limit })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading claims</p>

  const totalPages = Math.ceil((data.total || 0) / limit)

  return (
    <section>
      <h2>Claims explorer</h2>
      <p className="meta">Extractions that include at least one quantitative claim (numbers = tradable signal). Total: {data.total ?? 0}</p>

      <ul className="list">
        {(data.items || []).map((item) => (
          <li key={`${item.article.source}-${item.article.source_id}`}>
            <Link to={`/extractions/${encodeURIComponent(item.article.source)}/${encodeURIComponent(item.article.source_id)}`}>
              {item.article.title || item.article.source_id}
            </Link>
            <span className="source">{item.article.source}</span>
            {item.extraction?.claims?.filter((c) => c.quantitative).length > 0 && (
              <ul className="detail extraction" style={{ marginTop: '0.5rem', paddingLeft: '1rem' }}>
                {item.extraction.claims.filter((c) => c.quantitative).map((c, i) => (
                  <li key={i}>{c.statement}</li>
                ))}
              </ul>
            )}
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
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

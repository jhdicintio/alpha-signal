import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getArticles } from '../api'

export default function ArticlesList() {
  const [data, setData] = useState({ items: [], total: 0, limit: 50, offset: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const limit = 20

  useEffect(() => {
    setLoading(true)
    setError(null)
    getArticles({ limit, offset: page * limit })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [page])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading articles</p>

  const totalPages = Math.ceil(data.total / limit)

  return (
    <section>
      <h2>Articles</h2>
      <p className="meta">Total: {data.total}</p>
      <ul className="list">
        {data.items.map((art) => (
          <li key={`${art.source}-${art.source_id}`}>
            <Link to={`/articles/${encodeURIComponent(art.source)}/${encodeURIComponent(art.source_id)}`}>
              {art.title || art.source_id}
            </Link>
            <span className="source">{art.source}</span>
            {art.publication_date && <span className="meta"> · {art.publication_date}</span>}
          </li>
        ))}
      </ul>
      {totalPages > 1 && (
        <nav className="pagination">
          <button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <span>Page {page + 1} of {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </nav>
      )}
    </section>
  )
}

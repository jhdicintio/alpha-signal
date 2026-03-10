import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getExtractions } from '../api'

export default function ExtractionsList() {
  const [searchParams] = useSearchParams()
  const [data, setData] = useState({ items: [], total: 0, limit: 50, offset: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [page, setPage] = useState(0)
  const limit = 20

  const sector = searchParams.get('sector') ?? undefined
  const maturity = searchParams.get('maturity') ?? undefined
  const sentiment = searchParams.get('sentiment') ?? undefined
  const novelty = searchParams.get('novelty') ?? undefined
  const technology = searchParams.get('technology') ?? undefined
  const quantitative_claims = searchParams.get('quantitative_claims') === '1'
  const sort = searchParams.get('sort') ?? undefined
  const order = searchParams.get('order') ?? undefined

  useEffect(() => {
    setLoading(true)
    setError(null)
    const params = {
      limit,
      offset: page * limit,
      sector,
      maturity,
      sentiment,
      novelty,
      technology,
      sort,
      order,
    }
    if (quantitative_claims) params.quantitative_claims = true
    getExtractions(params)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [page, sector, maturity, sentiment, novelty, technology, quantitative_claims, sort, order])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading extractions</p>

  const totalPages = Math.ceil(data.total / limit)

  const filterDesc = [sector, maturity, sentiment, novelty, technology].filter(Boolean).join(' · ')
  return (
    <section>
      <h2>Extractions</h2>
      <p className="meta">
        Total: {data.total}
        {filterDesc && ` (filtered: ${filterDesc})`}
      </p>
      <ul className="list">
        {data.items.map((item) => (
          <li key={`${item.article.source}-${item.article.source_id}`}>
            <Link to={`/extractions/${encodeURIComponent(item.article.source)}/${encodeURIComponent(item.article.source_id)}`}>
              {item.article.title || item.article.source_id}
            </Link>
            <span className="source">{item.article.source}</span>
            {item.extraction?.summary && (
              <p className="summary">{item.extraction.summary}</p>
            )}
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

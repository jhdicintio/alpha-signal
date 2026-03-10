import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getAggregates, getExtractions } from '../api'

export default function Discovery() {
  const [agg, setAgg] = useState(null)
  const [recent, setRecent] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([
      getAggregates({ top: 25 }),
      getExtractions({
        novelty: 'novel',
        sentiment: 'optimistic',
        limit: 10,
        sort: 'publication_date',
        order: 'desc',
      }),
    ])
      .then(([aggData, listData]) => {
        setAgg(aggData)
        setRecent(listData)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading discovery</p>
  if (!agg) return null

  const topSectors = agg.top_sectors || []
  const topTechnologies = agg.top_technologies || []

  return (
    <section>
      <h2>What&apos;s hot</h2>
      <p className="meta">Top sectors and technologies by mention count, plus recent novel + optimistic extractions.</p>

      <div className="chart-section">
        <h3>Top sectors</h3>
        <ul className="list">
          {topSectors.map(({ sector, count }) => (
            <li key={sector}>
              <Link to={`/explore/sector/${encodeURIComponent(sector)}`}>{sector}</Link>
              <span className="bar-value" style={{ marginLeft: '0.5rem' }}>{count}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="chart-section">
        <h3>Top technologies</h3>
        <ul className="list">
          {topTechnologies.map((t) => (
            <li key={`${t.technology}-${t.sector}`}>
              <strong>{t.technology}</strong>
              <span className="meta" style={{ marginLeft: '0.5rem' }}>({t.sector})</span>
              <span className="bar-value" style={{ marginLeft: '0.5rem' }}>{t.count}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="chart-section">
        <h3>Recent novel + optimistic</h3>
        <p className="meta">Latest extractions that are both novel and optimistic.</p>
        {recent.items.length === 0 ? (
          <p className="meta">None found.</p>
        ) : (
          <ul className="list">
            {recent.items.map((item) => (
              <li key={`${item.article.source}-${item.article.source_id}`}>
                <Link to={`/extractions/${encodeURIComponent(item.article.source)}/${encodeURIComponent(item.article.source_id)}`}>
                  {item.article.title || item.article.source_id}
                </Link>
                <span className="source">{item.article.source}</span>
                {item.extraction?.summary && <p className="summary">{item.extraction.summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

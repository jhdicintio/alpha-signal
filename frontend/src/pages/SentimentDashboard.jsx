import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getAggregates, getExtractions } from '../api'

export default function SentimentDashboard() {
  const [agg, setAgg] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getAggregates()
      .then(setAgg)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading dashboard</p>
  if (!agg) return null

  const bySentiment = agg.by_sentiment || {}
  const byNovelty = agg.by_novelty || {}
  const totalSentiment = Object.values(bySentiment).reduce((s, n) => s + n, 0)
  const totalNovelty = Object.values(byNovelty).reduce((s, n) => s + n, 0)

  return (
    <section>
      <h2>Sentiment & novelty</h2>
      <p className="meta">Where is the optimism? How much is novel vs incremental?</p>

      <div className="dashboard-grid">
        <div className="dashboard-card">
          <h3>By sentiment</h3>
          <ul className="segment-list">
            {['optimistic', 'neutral', 'cautious', 'negative'].map((key) => {
              const count = bySentiment[key] || 0
              const pct = totalSentiment ? (count / totalSentiment) * 100 : 0
              return (
                <li key={key}>
                  <span>{key}</span>
                  <span className="segment-bar-wrap">
                    <span className="segment-bar" style={{ width: `${pct}%` }} />
                  </span>
                  <span>{count}</span>
                </li>
              )
            })}
          </ul>
        </div>
        <div className="dashboard-card">
          <h3>By novelty</h3>
          <ul className="segment-list">
            {['novel', 'incremental', 'review'].map((key) => {
              const count = byNovelty[key] || 0
              const pct = totalNovelty ? (count / totalNovelty) * 100 : 0
              return (
                <li key={key}>
                  <span>{key}</span>
                  <span className="segment-bar-wrap">
                    <span className="segment-bar" style={{ width: `${pct}%` }} />
                  </span>
                  <span>{count}</span>
                </li>
              )
            })}
          </ul>
        </div>
      </div>

      <h3 style={{ marginTop: '1.5rem' }}>High-signal: novel + optimistic</h3>
      <p className="meta">Extractions that are both novel and optimistic.</p>
      <NovelOptimisticList />

      <p className="meta" style={{ marginTop: '1.5rem' }}>
        <Link to="/explore">← Back to Explore</Link>
      </p>
    </section>
  )
}

function NovelOptimisticList() {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    getExtractions({ novelty: 'novel', sentiment: 'optimistic', limit: 20, sort: 'publication_date', order: 'desc' })
      .then(setData)
      .finally(() => setLoading(false))
  }, [])
  if (loading) return <p className="loading">Loading…</p>
  if (data.items.length === 0) return <p className="meta">None found.</p>
  return (
    <ul className="list" style={{ marginTop: '0.5rem' }}>
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
  )
}

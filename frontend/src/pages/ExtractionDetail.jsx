import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getExtraction } from '../api'

export default function ExtractionDetail() {
  const { source, sourceId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!source || !sourceId) return
    setLoading(true)
    setError(null)
    getExtraction(source, sourceId)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [source, sourceId])

  if (error) return <p className="error">Error: {error}</p>
  if (loading) return <p className="loading">Loading</p>
  if (!data) return null

  const { article, extraction } = data

  return (
    <section className="detail">
      <p><Link to="/extractions">← Back to extractions</Link></p>
      <header>
        <h2>{article.title}</h2>
        <p className="meta">
          {article.source} / {article.source_id}
          {article.publication_date && ` · ${article.publication_date}`}
        </p>
      </header>
      {article.abstract && <p className="abstract">{article.abstract}</p>}
      {extraction && (
        <div className="extraction">
          <h3>Summary</h3>
          <p>{extraction.summary}</p>
          <p className="meta">Novelty: {extraction.novelty} · Sentiment: {extraction.sentiment}</p>
          {extraction.technologies?.length > 0 && (
            <>
              <h3>Technologies</h3>
              <ul>
                {extraction.technologies.map((t, i) => (
                  <li key={i}>
                    <strong>{t.technology}</strong> ({t.sector}, {t.maturity})
                    <p>{t.relevance}</p>
                  </li>
                ))}
              </ul>
            </>
          )}
          {extraction.claims?.length > 0 && (
            <>
              <h3>Claims</h3>
              <ul>
                {extraction.claims.map((c, i) => (
                  <li key={i}>{c.statement} {c.quantitative ? '(quantitative)' : ''}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}

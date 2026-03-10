import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getArticle } from '../api'

export default function ArticleDetail() {
  const { source, sourceId } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!source || !sourceId) return
    setLoading(true)
    setError(null)
    getArticle(source, sourceId, true)
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
      <p><Link to="/articles">← Back to articles</Link></p>
      <header>
        <h2>{article.title}</h2>
        <p className="meta">
          {article.source} / {article.source_id}
          {article.publication_date && ` · ${article.publication_date}`}
        </p>
      </header>
      {article.abstract && <p className="abstract">{article.abstract}</p>}
      {extraction && (
        <p>
          <Link to={`/extractions/${encodeURIComponent(article.source)}/${encodeURIComponent(article.source_id)}`}>
            View extraction →
          </Link>
        </p>
      )}
    </section>
  )
}

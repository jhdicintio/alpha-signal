import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getStats } from '../api'

export default function Home() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <section>
      <h1>Alpha Signal</h1>
      <p>Scientific articles and trading-relevant extractions.</p>
      {error && <p className="error">Error: {error}</p>}
      {stats && (
        <div className="stats">
          <p><strong>{stats.articles}</strong> articles</p>
          <p><strong>{stats.extractions}</strong> extractions</p>
        </div>
      )}
      <nav className="nav-links">
        <Link to="/explore">Explore</Link>
        <Link to="/extractions">Browse extractions</Link>
        <Link to="/articles">Browse articles</Link>
      </nav>
    </section>
  )
}

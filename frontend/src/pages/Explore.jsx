import { Link } from 'react-router-dom'

export default function Explore() {
  return (
    <section>
      <h2>Explore</h2>
      <p className="meta">Visualizations and aggregation over extractions.</p>
      <nav className="explore-hub">
        <Link to="/explore/landscape">Sector landscape</Link>
        <Link to="/explore/sentiment">Sentiment & novelty</Link>
        <Link to="/explore/maturity">Maturity pipeline</Link>
        <Link to="/explore/trends">Trends over time</Link>
        <Link to="/explore/discovery">What&apos;s hot</Link>
        <Link to="/explore/claims">Claims explorer</Link>
        <Link to="/explore/compare">Compare sectors</Link>
      </nav>
    </section>
  )
}

import { Link, Routes, Route } from 'react-router-dom'
import Home from './pages/Home'
import ExtractionsList from './pages/ExtractionsList'
import ExtractionDetail from './pages/ExtractionDetail'
import ArticlesList from './pages/ArticlesList'
import ArticleDetail from './pages/ArticleDetail'
import Explore from './pages/Explore'
import Landscape from './pages/Landscape'
import SentimentDashboard from './pages/SentimentDashboard'
import SectorDrillDown from './pages/SectorDrillDown'
import MaturityPipeline from './pages/MaturityPipeline'
import Trends from './pages/Trends'
import Discovery from './pages/Discovery'
import ClaimsExplorer from './pages/ClaimsExplorer'
import Compare from './pages/Compare'
import Workflows from './pages/Workflows'
import './App.css'

function App() {
  return (
    <div className="app">
      <nav className="topnav">
        <Link to="/" className="brand">Alpha Signal</Link>
        <div className="nav-links">
          <Link to="/explore">Explore</Link>
          <Link to="/extractions">Extractions</Link>
          <Link to="/articles">Articles</Link>
          <Link to="/workflows">Workflows</Link>
        </div>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/explore/landscape" element={<Landscape />} />
          <Route path="/explore/sentiment" element={<SentimentDashboard />} />
          <Route path="/explore/sector/:sector" element={<SectorDrillDown />} />
          <Route path="/explore/maturity" element={<MaturityPipeline />} />
          <Route path="/explore/trends" element={<Trends />} />
          <Route path="/explore/discovery" element={<Discovery />} />
          <Route path="/explore/claims" element={<ClaimsExplorer />} />
          <Route path="/explore/compare" element={<Compare />} />
          <Route path="/extractions" element={<ExtractionsList />} />
          <Route path="/extractions/:source/:sourceId" element={<ExtractionDetail />} />
          <Route path="/articles" element={<ArticlesList />} />
          <Route path="/articles/:source/:sourceId" element={<ArticleDetail />} />
          <Route path="/workflows" element={<Workflows />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

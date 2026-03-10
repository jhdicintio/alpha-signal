import { useState, useEffect, useCallback } from 'react'
import {
  startIngest,
  startExtract,
  startPipeline,
  listJobs,
  getJob,
  getDefaultPrompt,
} from '../api'

const JOB_STATUS_LABELS = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

function JobStatusBadge({ status }) {
  const c = status === 'completed' ? 'workflows-status-ok' : status === 'failed' ? 'workflows-status-err' : 'workflows-status-pending'
  return <span className={`workflows-badge ${c}`}>{JOB_STATUS_LABELS[status] ?? status}</span>
}

export default function Workflows() {
  const [jobs, setJobs] = useState({ items: [], limit: 20, offset: 0 })
  const [jobsLoading, setJobsLoading] = useState(true)
  const [jobsError, setJobsError] = useState(null)
  const [lastJobId, setLastJobId] = useState(null)
  const [submitError, setSubmitError] = useState(null)
  const [submitSuccess, setSubmitSuccess] = useState(null)
  const [ingestQuery, setIngestQuery] = useState('')
  const [ingestDateFrom, setIngestDateFrom] = useState('')
  const [ingestDateTo, setIngestDateTo] = useState('')
  const [ingestMaxResults, setIngestMaxResults] = useState('')
  const [extractModel, setExtractModel] = useState('gpt-4o-mini')
  const [extractBudget, setExtractBudget] = useState('1.0')
  const [extractSkipExisting, setExtractSkipExisting] = useState(true)
  const [pipelineQuery, setPipelineQuery] = useState('')
  const [pipelineDateFrom, setPipelineDateFrom] = useState('')
  const [pipelineDateTo, setPipelineDateTo] = useState('')
  const [pipelineModel, setPipelineModel] = useState('gpt-4o-mini')
  const [pipelineBudget, setPipelineBudget] = useState('1.0')
  const [extractSystemPrompt, setExtractSystemPrompt] = useState('')
  const [pipelineSystemPrompt, setPipelineSystemPrompt] = useState('')
  const [defaultPrompt, setDefaultPrompt] = useState(null)
  const [defaultPromptLoading, setDefaultPromptLoading] = useState(false)
  const [submitting, setSubmitting] = useState(null)

  const loadJobs = useCallback(() => {
    setJobsLoading(true)
    setJobsError(null)
    listJobs({ limit: 20, offset: 0 })
      .then(setJobs)
      .catch((e) => setJobsError(e.message))
      .finally(() => setJobsLoading(false))
  }, [])

  useEffect(() => {
    loadJobs()
  }, [loadJobs])

  // Poll last job while it's pending or running
  useEffect(() => {
    if (!lastJobId) return
    const t = setInterval(() => {
      getJob(lastJobId)
        .then((job) => {
          if (job.status === 'pending' || job.status === 'running') return
          clearInterval(t)
          loadJobs()
        })
        .catch(() => clearInterval(t))
    }, 2000)
    return () => clearInterval(t)
  }, [lastJobId, loadJobs])

  const clearFeedback = () => {
    setSubmitError(null)
    setSubmitSuccess(null)
  }

  const loadDefaultPrompt = useCallback(() => {
    if (defaultPrompt !== null) return
    setDefaultPromptLoading(true)
    getDefaultPrompt()
      .then((data) => setDefaultPrompt(data.system_prompt || ''))
      .catch(() => setDefaultPrompt(''))
      .finally(() => setDefaultPromptLoading(false))
  }, [defaultPrompt])

  const handleIngest = async (e) => {
    e.preventDefault()
    clearFeedback()
    const query = ingestQuery.trim() || undefined
    const date_from = ingestDateFrom.trim() || undefined
    const date_to = ingestDateTo.trim() || undefined
    if (!query && !date_from && !date_to) {
      setSubmitError('Provide at least one of: query, date from, or date to.')
      return
    }
    const body = { query, date_from, date_to }
    if (ingestMaxResults.trim()) {
      const n = parseInt(ingestMaxResults, 10)
      if (!Number.isNaN(n)) body.max_results_per_source = n
    }
    setSubmitting('ingest')
    try {
      const { job_id } = await startIngest(body)
      setLastJobId(job_id)
      setSubmitSuccess(`Ingest started. Job ID: ${job_id}`)
      loadJobs()
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(null)
    }
  }

  const handleExtract = async (e) => {
    e.preventDefault()
    clearFeedback()
    const body = {
      model: extractModel.trim() || 'gpt-4o-mini',
      budget_usd: parseFloat(extractBudget) || 1.0,
      skip_existing: extractSkipExisting,
    }
    if (extractSystemPrompt.trim()) body.system_prompt = extractSystemPrompt.trim()
    setSubmitting('extract')
    try {
      const { job_id } = await startExtract(body)
      setLastJobId(job_id)
      setSubmitSuccess(`Extract started. Job ID: ${job_id}`)
      loadJobs()
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(null)
    }
  }

  const handlePipeline = async (e) => {
    e.preventDefault()
    clearFeedback()
    const query = pipelineQuery.trim() || undefined
    const date_from = pipelineDateFrom.trim() || undefined
    const date_to = pipelineDateTo.trim() || undefined
    if (!query && !date_from && !date_to) {
      setSubmitError('Provide at least one of: query, date from, or date to.')
      return
    }
    const body = {
      query,
      date_from,
      date_to,
      model: pipelineModel.trim() || 'gpt-4o-mini',
      budget_usd: parseFloat(pipelineBudget) || 1.0,
    }
    if (pipelineSystemPrompt.trim()) body.system_prompt = pipelineSystemPrompt.trim()
    setSubmitting('pipeline')
    try {
      const { job_id } = await startPipeline(body)
      setLastJobId(job_id)
      setSubmitSuccess(`Pipeline started. Job ID: ${job_id}`)
      loadJobs()
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(null)
    }
  }

  return (
    <section className="workflows-page">
      <h2>Workflows</h2>
      <p className="meta">Trigger ingestion, extraction, or the full pipeline (ingest + extract).</p>

      <div className="workflows-default-prompt">
        <button type="button" className="workflows-link" onClick={loadDefaultPrompt} disabled={defaultPromptLoading}>
          {defaultPromptLoading ? 'Loading…' : 'Show default extraction prompt'}
        </button>
        {defaultPrompt !== null && (
          <textarea
            readOnly
            rows={10}
            value={defaultPrompt}
            className="workflows-prompt-default"
            aria-label="Default extraction prompt (read-only)"
          />
        )}
      </div>

      {(submitError || submitSuccess) && (
        <div className={`workflows-feedback ${submitError ? 'workflows-feedback-error' : 'workflows-feedback-success'}`}>
          {submitError || submitSuccess}
        </div>
      )}

      <div className="workflows-forms">
        <div className="workflows-card">
          <h3>Ingest</h3>
          <p className="workflows-desc">Fetch articles from configured sources by query and/or date range.</p>
          <form onSubmit={handleIngest} className="workflows-form">
            <label>
              Query
              <input
                type="text"
                value={ingestQuery}
                onChange={(e) => setIngestQuery(e.target.value)}
                placeholder="e.g. machine learning"
              />
            </label>
            <label>
              Date from
              <input
                type="date"
                value={ingestDateFrom}
                onChange={(e) => setIngestDateFrom(e.target.value)}
              />
            </label>
            <label>
              Date to
              <input
                type="date"
                value={ingestDateTo}
                onChange={(e) => setIngestDateTo(e.target.value)}
              />
            </label>
            <label>
              Max results per source
              <input
                type="number"
                min={1}
                value={ingestMaxResults}
                onChange={(e) => setIngestMaxResults(e.target.value)}
                placeholder="optional"
              />
            </label>
            <button type="submit" disabled={!!submitting}>
              {submitting === 'ingest' ? 'Starting…' : 'Start ingest'}
            </button>
          </form>
        </div>

        <div className="workflows-card">
          <h3>Extract</h3>
          <p className="workflows-desc">Run extraction on articles already in the cache (LLM-based). Optionally override the system prompt to iterate on extraction behavior.</p>
          <form onSubmit={handleExtract} className="workflows-form">
            <label>
              Model
              <input
                type="text"
                value={extractModel}
                onChange={(e) => setExtractModel(e.target.value)}
                placeholder="gpt-4o-mini"
              />
            </label>
            <label>
              Budget (USD)
              <input
                type="number"
                min={0}
                step={0.1}
                value={extractBudget}
                onChange={(e) => setExtractBudget(e.target.value)}
              />
            </label>
            <label className="workflows-check">
              <input
                type="checkbox"
                checked={extractSkipExisting}
                onChange={(e) => setExtractSkipExisting(e.target.checked)}
              />
              Skip existing extractions
            </label>
            <div className="workflows-prompt-block">
              <label htmlFor="extract-prompt">
                Custom extraction prompt
              </label>
              <p id="extract-prompt-hint" className="workflows-prompt-hint">Override the default system prompt used by the LLM for this run. Leave empty to use the default.</p>
              <textarea
                id="extract-prompt"
                rows={6}
                value={extractSystemPrompt}
                onChange={(e) => setExtractSystemPrompt(e.target.value)}
                placeholder="e.g. Focus on quantitative claims and technology maturity. Output JSON with summary, technologies, and claims."
                className="workflows-prompt-input"
                aria-describedby="extract-prompt-hint"
              />
            </div>
            <button type="submit" disabled={!!submitting}>
              {submitting === 'extract' ? 'Starting…' : 'Start extract'}
            </button>
          </form>
        </div>

        <div className="workflows-card">
          <h3>Pipeline</h3>
          <p className="workflows-desc">Run ingest then extract in one job.</p>
          <form onSubmit={handlePipeline} className="workflows-form">
            <label>
              Query
              <input
                type="text"
                value={pipelineQuery}
                onChange={(e) => setPipelineQuery(e.target.value)}
                placeholder="e.g. machine learning"
              />
            </label>
            <label>
              Date from
              <input
                type="date"
                value={pipelineDateFrom}
                onChange={(e) => setPipelineDateFrom(e.target.value)}
              />
            </label>
            <label>
              Date to
              <input
                type="date"
                value={pipelineDateTo}
                onChange={(e) => setPipelineDateTo(e.target.value)}
              />
            </label>
            <label>
              Model
              <input
                type="text"
                value={pipelineModel}
                onChange={(e) => setPipelineModel(e.target.value)}
                placeholder="gpt-4o-mini"
              />
            </label>
            <label>
              Budget (USD)
              <input
                type="number"
                min={0}
                step={0.1}
                value={pipelineBudget}
                onChange={(e) => setPipelineBudget(e.target.value)}
              />
            </label>
            <div className="workflows-prompt-block">
              <label htmlFor="pipeline-prompt">
                Custom extraction prompt
              </label>
              <p id="pipeline-prompt-hint" className="workflows-prompt-hint">Override the default system prompt used by the LLM for the extraction step. Leave empty to use the default.</p>
              <textarea
                id="pipeline-prompt"
                rows={6}
                value={pipelineSystemPrompt}
                onChange={(e) => setPipelineSystemPrompt(e.target.value)}
                placeholder="e.g. Focus on quantitative claims and technology maturity. Output JSON with summary, technologies, and claims."
                className="workflows-prompt-input"
                aria-describedby="pipeline-prompt-hint"
              />
            </div>
            <button type="submit" disabled={!!submitting}>
              {submitting === 'pipeline' ? 'Starting…' : 'Start pipeline'}
            </button>
          </form>
        </div>
      </div>

      <div className="workflows-jobs">
        <div className="workflows-jobs-header">
          <h3>Recent jobs</h3>
          <button type="button" onClick={loadJobs} disabled={jobsLoading}>
            {jobsLoading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
        {jobsError && <p className="error">{jobsError}</p>}
        {jobsLoading && jobs.items.length === 0 && <p className="loading">Loading jobs</p>}
        {!jobsLoading && jobs.items.length === 0 && !jobsError && (
          <p className="meta">No jobs yet. Start an ingest, extract, or pipeline above.</p>
        )}
        {!jobsLoading && jobs.items.length > 0 && (
          <ul className="list workflows-job-list">
            {jobs.items.map((job) => (
              <li key={job.job_id}>
                <div className="workflows-job-row">
                  <span className="workflows-job-id">{job.job_id}</span>
                  <span className="workflows-job-type">{job.job_type}</span>
                  <JobStatusBadge status={job.status} />
                  <span className="meta workflows-job-time">{job.created_at}</span>
                </div>
                {job.error && <p className="error workflows-job-err">{job.error}</p>}
                {job.result && (
                  <pre className="workflows-job-result">{JSON.stringify(job.result, null, 2)}</pre>
                )}
                {job.params && Object.keys(job.params).length > 0 && (
                  <p className="meta workflows-job-params">
                    Params: {JSON.stringify(job.params)}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

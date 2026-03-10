const API_BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

export async function getHealth() {
  return request('/health');
}

export async function getStats() {
  return request('/stats');
}

export async function getExtractions(params = {}) {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', params.limit);
  if (params.offset != null) sp.set('offset', params.offset);
  if (params.source) sp.set('source', params.source);
  if (params.extraction_model) sp.set('extraction_model', params.extraction_model);
  if (params.sector) sp.set('sector', params.sector);
  if (params.maturity) sp.set('maturity', params.maturity);
  if (params.sentiment) sp.set('sentiment', params.sentiment);
  if (params.novelty) sp.set('novelty', params.novelty);
  if (params.technology) sp.set('technology', params.technology);
  if (params.quantitative_claims) sp.set('quantitative_claims', params.quantitative_claims);
  if (params.sort) sp.set('sort', params.sort);
  if (params.order) sp.set('order', params.order);
  const q = sp.toString();
  return request(`/extractions${q ? `?${q}` : ''}`);
}

export async function getAggregates(params = {}) {
  const sp = new URLSearchParams();
  if (params.sector) sp.set('sector', params.sector);
  if (params.top != null) sp.set('top', params.top);
  const q = sp.toString();
  return request(`/extractions/aggregates${q ? `?${q}` : ''}`);
}

export async function getTrends(params = {}) {
  const sp = new URLSearchParams();
  if (params.from) sp.set('from', params.from);
  if (params.to) sp.set('to', params.to);
  if (params.sector) sp.set('sector', params.sector);
  if (params.group_by) sp.set('group_by', params.group_by || 'month');
  const q = sp.toString();
  return request(`/extractions/trends${q ? `?${q}` : ''}`);
}

export async function getExtraction(source, sourceId) {
  return request(`/extractions/${encodeURIComponent(source)}/${encodeURIComponent(sourceId)}`);
}

export async function getArticles(params = {}) {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', params.limit);
  if (params.offset != null) sp.set('offset', params.offset);
  if (params.source) sp.set('source', params.source);
  if (params.publication_date_from) sp.set('publication_date_from', params.publication_date_from);
  if (params.publication_date_to) sp.set('publication_date_to', params.publication_date_to);
  const q = sp.toString();
  return request(`/articles${q ? `?${q}` : ''}`);
}

export async function getArticle(source, sourceId, withExtraction = false) {
  const q = withExtraction ? '?with_extraction=1' : '';
  return request(`/articles/${encodeURIComponent(source)}/${encodeURIComponent(sourceId)}${q}`);
}

// ---- Jobs (ingest / extract / pipeline) ----

export async function startIngest(body) {
  const res = await fetch(`${API_BASE}/jobs/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export async function startExtract(body) {
  const res = await fetch(`${API_BASE}/jobs/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export async function startPipeline(body) {
  const res = await fetch(`${API_BASE}/jobs/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

export async function getJob(jobId) {
  return request(`/jobs/${encodeURIComponent(jobId)}`);
}

/** Default extraction system prompt (for viewing/copying when iterating on prompts). */
export async function getDefaultPrompt() {
  return request('/jobs/default-prompt');
}

export async function listJobs(params = {}) {
  const sp = new URLSearchParams();
  if (params.limit != null) sp.set('limit', params.limit);
  if (params.offset != null) sp.set('offset', params.offset);
  if (params.type) sp.set('type', params.type);
  const q = sp.toString();
  return request(`/jobs${q ? `?${q}` : ''}`);
}

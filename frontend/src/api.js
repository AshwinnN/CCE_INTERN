const request = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      message = body.detail || message
    } catch {}
    throw new Error(message)
  }
  return response.json()
}

export const api = {
  summary: () => request('/api/v1/dashboard/summary'),
  ingestionRuns: () => request('/api/v1/ingestion/runs'),
  ingest: (document_name) => request('/api/v1/ingestion/run', {
    method: 'POST', body: JSON.stringify({ document_name, source: 'customer-contract' }),
  }),
  proposals: (status = '') => request(`/api/v1/proposals${status ? `?status=${status}` : ''}`),
  proposal: (id) => request(`/api/v1/proposals/${id}`),
  approve: (id, comment = '') => request(`/api/v1/proposals/${id}/approve`, { method: 'POST', body: JSON.stringify({ comment }) }),
  reject: (id, comment = '') => request(`/api/v1/proposals/${id}/reject`, { method: 'POST', body: JSON.stringify({ comment }) }),
  packages: () => request('/api/v1/packages'),
  createPackage: (payload) => request('/api/v1/packages', { method: 'POST', body: JSON.stringify(payload) }),
  compare: (payload) => request('/api/v1/questions/compare', { method: 'POST', body: JSON.stringify(payload) }),
}

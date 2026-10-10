// All network access in one place. VITE_API_BASE is empty in dev (Vite proxies /api and /ws) and when the
// FastAPI server also serves the built frontend (single Render service); set it for a split deployment.
const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

async function request(path, { method = 'GET', body, token } = {}) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  const res = await fetch(`${BASE}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (!res.ok) {
    const err = new Error(data?.detail || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

export const health = () => request('/api/health')
export const rubrics = () => request('/api/rubrics')
export const createSession = (payload) => request('/api/sessions', { method: 'POST', body: payload })
export const getSession = (id, token) => request(`/api/sessions/${id}`, { token })
export const deleteSession = (id, token) => request(`/api/sessions/${id}`, { method: 'DELETE', token })
export const regenerate = (id, token) => request(`/api/sessions/${id}/report`, { method: 'POST', token })
export const pdfUrl = (id, token) => `${BASE}/api/sessions/${id}/report.pdf?token=${encodeURIComponent(token)}`
export const thumbUrl = (id, name, token) => `${BASE}/api/sessions/${id}/thumb/${name}?token=${encodeURIComponent(token)}`

export function wsUrl(path) {
  if (BASE) return BASE.replace(/^http/, 'ws') + path
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}${path}`
}

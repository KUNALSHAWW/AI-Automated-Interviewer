// Sessions live on the server, but the secret token stays in this browser only.
const KEY = 'navai.sessions.v1'

export function listHistory() {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] }
}

function save(items) {
  try { localStorage.setItem(KEY, JSON.stringify(items.slice(0, 50))) } catch { /* storage full or blocked */ }
}

export function rememberSession(entry) {
  const items = listHistory().filter((x) => x.id !== entry.id)
  save([{ ...entry }, ...items])
}

export function updateSession(id, patch) {
  save(listHistory().map((x) => (x.id === id ? { ...x, ...patch } : x)))
}

export function forgetSession(id) {
  save(listHistory().filter((x) => x.id !== id))
}

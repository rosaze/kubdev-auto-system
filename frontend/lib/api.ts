export async function apiGet<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("/") ? `/api${path}` : `/api/${path}`
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`GET ${url} failed: ${res.status} ${text}`)
  }
  return (await res.json()) as T
}

export async function apiPost<T = unknown, B = unknown>(path: string, body?: B, init?: RequestInit): Promise<T> {
  const url = path.startsWith("/") ? `/api${path}` : `/api/${path}`
  const res = await fetch(url, {
    method: "POST",
    ...init,
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(init?.headers || {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`POST ${url} failed: ${res.status} ${text}`)
  }
  return (await res.json()) as T
}

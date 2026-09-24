export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : {
      'Content-Type': 'application/json', ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      const parsed = JSON.parse(body);
      detail = typeof parsed.detail === 'string' ? parsed.detail : JSON.stringify(parsed.detail);
    } catch { /* Non-JSON server failures remain visible in the error message. */ }
    throw new Error(`请求失败（${response.status}）：${detail}`);
  }
  return response.status === 204 ? undefined as T : response.json();
}

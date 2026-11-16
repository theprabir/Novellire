export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function errorFromResponse(response) {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') detail = data.detail;
    else if (Array.isArray(data.detail)) {
      detail = data.detail.map((item) => item.msg || JSON.stringify(item)).join('; ');
    }
  } catch (error) { /* keep the status text */ }
  return new ApiError(detail, response.status);
}

async function request(method, path, body) {
  const options = { method, headers: { Accept: 'application/json' } };
  if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new ApiError('Cannot reach the Novellire server. Is it still running?', 0);
  }

  if (!response.ok) throw await errorFromResponse(response);

  if (response.status === 204) return null;
  return response.json();
}

async function stream(path, body, onEvent) {
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: {
        Accept: 'application/x-ndjson',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body === undefined ? {} : body),
    });
  } catch (error) {
    throw new ApiError('Cannot reach the Novellire server. Is it still running?', 0);
  }

  if (!response.ok) throw await errorFromResponse(response);
  if (!response.body) {
    throw new ApiError('This browser cannot read the progress stream.', 0);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf('\n');
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line));
      newline = buffer.indexOf('\n');
    }
  }
  const tail = (buffer + decoder.decode()).trim();
  if (tail) onEvent(JSON.parse(tail));
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body === undefined ? {} : body),
  patch: (path, body) => request('PATCH', path, body),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),
  stream,
};

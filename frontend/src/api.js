export async function api(path, body) {
  const form = body instanceof FormData;
  const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST',
    headers: {'X-ACE-Client':'1', ...(body !== undefined && !form ? {'Content-Type':'application/json'} : {})},
    body: body === undefined ? undefined : form ? body : JSON.stringify(body)});
  const result = await response.json().catch(() => ({detail:'The server returned an unexpected response.'}));
  if (!response.ok) throw new Error(Array.isArray(result.detail)
    ? result.detail.map(e => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('\n') : result.detail || 'Request failed.');
  return result;
}

// Reads a server-sent event stream: calls onStep for each progress step and returns the final result event.
export async function streamEvents(path, payload, onStep, failure = 'Request failed.') {
  const response = await fetch(path, {method:'POST',
    headers:{'X-ACE-Client':'1', 'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  if (!response.ok) {
    const result = await response.json().catch(() => ({detail:failure}));
    throw new Error(Array.isArray(result.detail)
      ? result.detail.map(e => `${e.loc.slice(1).join('.')}: ${e.msg}`).join('\n') : result.detail || failure);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', finalResult = null;
  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    for (const line of parts.flatMap(p => p.split('\n')).filter(l => l.startsWith('data: '))) {
      let data;
      try {data = JSON.parse(line.slice(6));} catch {continue;}
      if (data.type === 'step') onStep(data);
      else if (data.type === 'result') finalResult = data;
      else if (data.type === 'error') throw new Error(data.message);
    }
  }
  return finalResult;
}

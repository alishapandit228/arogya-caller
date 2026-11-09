export async function api(path, body, raw = false) {
  const response = await fetch('/voice' + path, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': raw ? body.type : 'application/json' },
    body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.error || 'Request failed. Please retry.')
  }
  return response.json()
}

export function signaling(kind, update, status) {
  let socket, retry, stopped = false
  const connect = () => {
    if (stopped) return
    socket = new WebSocket(location.origin.replace(/^http/, 'ws') + '/voice/ws/' + kind)
    socket.onopen = () => status('Connected')
    socket.onmessage = event => {
      try { update(JSON.parse(event.data)) } catch { status('Invalid server response') }
    }
    socket.onerror = () => status('Connection error')
    socket.onclose = async event => {
      if (stopped) return
      if (event.code === 4409) { status('Receiver is already open in another tab'); return }
      if (event.code === 1008) { status('Signaling rejected. Reload to reconnect.'); return }
      // Browsers report a refused handshake as 1006, hiding the server close code.
      let expired = event.code === 4401
      try {
        const check = await fetch('/voice/' + (kind === 'admin' ? 'admin/state' : 'me'), { credentials: 'same-origin' })
        expired ||= check.status === 401
      } catch { /* A network failure remains reconnectable. */ }
      if (stopped) return
      if (expired) { status('Access expired. Rejoin or sign in again.'); return }
      status('Disconnected — reconnecting')
      retry = setTimeout(connect, 3000)
    }
  }
  connect()
  return () => { stopped = true; clearTimeout(retry); socket?.close() }
}

export const closed = call => !call || ['completed', 'cancelled', 'failed', 'rejected'].includes(call.status)

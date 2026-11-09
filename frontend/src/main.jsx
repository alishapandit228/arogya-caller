import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api, signaling, closed } from './api'
import './style.css'

function Layout({ children, receiver = false }) {
  return <div className="min-h-screen bg-slate-950 text-slate-100">
    <header className="border-b border-slate-800 px-6 py-5 flex justify-between items-center">
      <a className="font-bold text-xl tracking-tight" href="/">Arogya <span className="text-teal-300">Caller</span></a>
      <span className="text-sm text-slate-400">{receiver ? 'Your private call space' : 'Local AI calling dashboard'}</span>
    </header><main className="max-w-6xl mx-auto px-5 py-8">{children}</main>
  </div>
}
const ErrorBox = ({ error }) => error && <p role="alert" className="rounded-xl bg-red-950 border border-red-700 p-4 my-4">{error}</p>
const Badge = ({ children }) => <span className="rounded-full bg-slate-800 px-3 py-1 text-sm text-teal-200">{children}</span>

function Dashboard() {
  const [logged, setLogged] = useState(false), [token, setToken] = useState('')
  const [error, setError] = useState(''), [state, setState] = useState({ recipients: [], calls: [] })
  const [connection, setConnection] = useState('Offline'), [roles, setRoles] = useState([])
  const [role, setRole] = useState('general'), [recipient, setRecipient] = useState('')
  const [name, setName] = useState(''), [invite, setInvite] = useState('')
  const [history, setHistory] = useState([]), [result, setResult] = useState(null), [busy, setBusy] = useState(false)
  useEffect(() => { api('/admin/state').then(s => { setState(s); setLogged(true) }).catch(() => {}) }, [])
  useEffect(() => {
    if (!logged) return
    api('/admin/roles').then(setRoles).catch(e => setError(e.message))
    const load = () => api('/admin/history').then(setHistory).catch(e => setError(e.message))
    load()
    const timer = setInterval(load, 5000)
    const stop = signaling('admin', setState, value => {
      setConnection(value)
      if (value.startsWith('Access expired')) { setLogged(false); setHistory([]); setResult(null); setInvite('') }
    })
    return () => { stop(); clearInterval(timer) }
  }, [logged])
  const act = async action => {
    setError(''); setBusy(true)
    try { await action() } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const login = event => {
    event.preventDefault()
    act(async () => { try { await api('/admin/login', { token }); setLogged(true) } finally { setToken('') } })
  }
  if (!logged) return <Layout><section className="panel max-w-lg mx-auto mt-12">
    <p className="eyebrow">ADMINISTRATOR</p><h1 className="text-3xl font-bold mb-3">Welcome to your call desk</h1>
    <p className="text-slate-400 mb-6">Sign in locally to connect a recipient and start a role-based AI conversation.</p>
    <form onSubmit={login}><label>Administrator token<input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} required minLength={32}/></label>
      <button disabled={busy}>Sign in</button></form><ErrorBox error={error}/>
    <p className="text-xs text-slate-500 mt-5">Your token is exchanged for a short-lived secure cookie. Never share it with recipients.</p>
  </section></Layout>
  const current = state.calls.find(c => !closed(c))
  return <Layout><div className="flex justify-between items-start mb-8"><div><p className="eyebrow">PHASE 2 · LOCAL VOICE</p><h1 className="text-3xl font-bold">Your call desk</h1></div>
    <div className="flex gap-3 items-center"><Badge>{connection}</Badge><button className="secondary" onClick={() => act(async () => { await api('/admin/logout', {}); setLogged(false) })}>Sign out</button></div></div>
    <ErrorBox error={error}/>
    <div className="grid md:grid-cols-2 gap-6">
      <section className="panel"><h2>Connect a recipient</h2><p className="muted">Create a single-use invitation. Ask the recipient to open it on this Wi-Fi and keep the page open.</p>
        <label>Recipient display name<input value={name} maxLength={60} onChange={e => setName(e.target.value)}/></label>
        <button disabled={busy || !name.trim()} onClick={() => act(async () => {
          const data = await api('/admin/recipients', { name })
          setInvite(location.origin + '/receive#join=' + encodeURIComponent(data.code))
        })}>Create private invitation</button>
        {invite && <div className="mt-4"><label>Invitation · expires in 5 minutes<input readOnly value={invite} onFocus={e => e.target.select()}/></label><p className="text-xs text-slate-400">Share privately. This invitation grants receiver access only.</p></div>}
      </section>
      <section className="panel"><h2>Start an AI call</h2><label>AI agent role<select value={role} onChange={e => setRole(e.target.value)}>{roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
        <label>Connected recipient<select value={recipient} onChange={e => setRecipient(e.target.value)}><option value="">Select recipient</option>{state.recipients.map(r => <option key={r.id} value={r.id} disabled={!r.online}>{r.name} · {r.online ? 'Available' : 'Offline'}</option>)}</select></label>
        <button disabled={busy || !recipient || !!current} onClick={() => act(async () => { await api('/admin/calls', { role_id: role, recipient_id: recipient }) })}>Initiate internet call</button>
        <p className="text-xs text-slate-400 mt-3">One local call at a time. No telephone number or paid service.</p>
      </section>
    </div>
    <section className="panel mt-6"><h2>Call activity</h2>{state.calls.length === 0 ? <p className="muted">No calls yet. Connect a recipient to begin.</p> : state.calls.map(c => <div className="flex flex-wrap justify-between items-center gap-3 py-3 border-b border-slate-800" key={c.id}>
      <div><strong>{state.recipients.find(r => r.id === c.recipient_id)?.name || 'Recipient'}</strong><p className="muted">{roles.find(r => r.id === c.role_id)?.name || c.role_id}</p></div><Badge>{c.status}</Badge>
      {!closed(c) && <button className="danger" onClick={() => act(() => api('/admin/calls/' + c.id + '/end', {}))}>End call</button>}
    </div>)}</section>
    <section className="panel mt-6"><h2>Session history & results</h2><p className="muted mb-4">Only explicitly confirmed sessions expose a final result.</p>
      <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Role</th><th>Created</th><th>Status</th><th>Result</th></tr></thead><tbody>{history.map(s => <tr key={s.id}><td>{s.role_id}</td><td>{new Date(s.created_at).toLocaleString()}</td><td>{s.status}</td><td>{s.status === 'completed' && <button className="secondary" onClick={() => act(async () => setResult(await api('/admin/sessions/' + s.id + '/result')))}>View JSON</button>}</td></tr>)}</tbody></table></div>
      {result && <pre className="mt-4 rounded-xl bg-slate-950 p-4 overflow-auto">{JSON.stringify(result, null, 2)}</pre>}
    </section>
  </Layout>
}

function Receiver() {
  const [code, setCode] = useState(() => new URLSearchParams(location.hash.slice(1)).get('join') || '')
  const [joined, setJoined] = useState(false), [connection, setConnection] = useState('Offline')
  const [name, setName] = useState(''), [call, setCall] = useState(null), [error, setError] = useState('')
  const [stage, setStage] = useState('Ready'), [transcript, setTranscript] = useState(''), [busy, setBusy] = useState(false)
  const [needsPlay, setNeedsPlay] = useState(false), [confirming, setConfirming] = useState(false)
  const player = useRef(null), recorder = useRef(null), stream = useRef(null), context = useRef(null)
  const timer = useRef(null), audioUrl = useRef(null), liveCall = useRef(null), mounted = useRef(true)
  liveCall.current = call
  function clearCapture() {
    clearInterval(timer.current)
    stream.current?.getTracks().forEach(t => t.stop()); stream.current = null
    context.current?.close().catch(() => {}); context.current = null
  }
  function silence() {
    if (recorder.current?.state === 'recording') { recorder.current.onstop = null; recorder.current.stop() }
    clearCapture()
    player.current?.pause()
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current)
    audioUrl.current = null; setNeedsPlay(false); setStage('Ready')
  }
  useEffect(() => {
    window.history.replaceState(null, '', '/receive')
    api('/me').then(s => { setJoined(true); setName(s.name) }).catch(() => {})
    return () => { mounted.current = false; silence() }
  }, [])
  useEffect(() => {
    if (!joined) return
    return signaling('receiver', s => {
      const next = s.calls.at(-1) || null
      setCall(next)
      if (closed(next) && next?.status !== 'completed') silence()
    }, value => {
      setConnection(value)
      if (value !== 'Connected') silence()
      if (value.startsWith('Access expired')) { setJoined(false); setCall(null); setName(''); setTranscript('') }
    })
  }, [joined])
  const play = async id => {
    const response = await fetch('/voice/calls/' + id + '/speech', { credentials: 'same-origin' })
    if (!response.ok) throw new Error('Speech is not ready. Try again or end the call.')
    if (!mounted.current || liveCall.current && liveCall.current.id !== id) return
    player.current?.pause()
    if (audioUrl.current) URL.revokeObjectURL(audioUrl.current)
    audioUrl.current = URL.createObjectURL(await response.blob())
    const audio = new Audio(audioUrl.current); player.current = audio
    audio.onended = () => { setStage('Your turn'); setNeedsPlay(false) }
    audio.onerror = () => { setError('Audio playback failed. Check your speaker and retry.'); setStage('Playback error'); setNeedsPlay(true) }
    setStage('AI speaking')
    try { await audio.play(); setNeedsPlay(false) } catch { setNeedsPlay(true); setStage('Tap Play reply to enable audio') }
  }
  const action = async value => {
    setBusy(true); setError('')
    try {
      if (['end', 'reject', 'refuse'].includes(value)) silence()
      const data = await api('/calls/' + call.id + '/action', { action: value })
      setCall(data); liveCall.current = data
      if (!closed(data) || data.status === 'completed') { setConfirming(data.message.startsWith('Please confirm')); await play(data.id) }
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const record = async () => {
    if (recorder.current?.state === 'recording') { recorder.current.stop(); return }
    if (!player.current?.paused && player.current) return
    setError(''); setNeedsPlay(false)
    try {
      if (!window.isSecureContext || !navigator.mediaDevices) throw new Error('Microphone requires trusted HTTPS. Follow the local certificate setup.')
      if (!window.MediaRecorder) throw new Error('This browser does not support recording. Try current Safari or Chrome.')
      const id = call.id
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false })
      if (closed(liveCall.current)) { clearCapture(); return }
      const type = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm'].find(t => MediaRecorder.isTypeSupported(t))
      const capture = new MediaRecorder(stream.current, type ? { mimeType: type } : {})
      recorder.current = capture
      const chunks = []
      capture.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }
      capture.onerror = () => { clearCapture(); setStage('Ready'); setError('Microphone recording failed') }
      capture.onstop = async () => {
        clearCapture()
        if (closed(liveCall.current) || liveCall.current?.id !== id) return
        setBusy(true); setStage('Transcribing & thinking')
        try {
          const blob = new Blob(chunks, { type: capture.mimeType || type || 'audio/webm' })
          const data = await api('/calls/' + id + '/audio', blob, true)
          setTranscript(data.transcription); setCall(data); liveCall.current = data
          setConfirming(data.message.startsWith('Please confirm'))
          if (!['cancelled', 'failed'].includes(data.status)) await play(id)
        } catch (e) { setError(e.message); setStage('Try recording again') }
        finally { setBusy(false) }
      }
      context.current = new AudioContext()
      const input = context.current.createMediaStreamSource(stream.current)
      const analyser = context.current.createAnalyser(); analyser.fftSize = 2048; input.connect(analyser)
      const samples = new Float32Array(analyser.fftSize)
      let started = performance.now(), lastVoice = started, heardVoice = false
      timer.current = setInterval(() => {
        analyser.getFloatTimeDomainData(samples)
        const energy = Math.sqrt(samples.reduce((total, sample) => total + sample * sample, 0) / samples.length)
        const now = performance.now()
        if (energy > 0.015) { heardVoice = true; lastVoice = now }
        if (now - started > 19000 || heardVoice && now - lastVoice > 1600 || !heardVoice && now - started > 7000) {
          if (capture.state === 'recording') capture.stop()
        }
      }, 100)
      capture.start(); setStage('Listening')
    } catch (e) { clearCapture(); setStage('Ready'); setError(e.name === 'NotAllowedError' ? 'Microphone access denied. Enable permission in browser settings.' : e.message) }
  }
  return <Layout receiver><section className="panel max-w-xl mx-auto">
    <p className="eyebrow">PRIVATE AI CONVERSATION</p><h1 className="text-3xl font-bold mb-3">{name ? 'Hello, ' + name : 'Your call space'}</h1>
    <p className="muted mb-5">Keep this page open to receive calls. You choose whether to answer and consent.</p><ErrorBox error={error}/>
    {!joined ? <form onSubmit={async e => {
      e.preventDefault(); setError(''); setBusy(true)
      try { const data = await api('/join', { code }); setName(data.name); setJoined(true); setCode('') }
      catch (e) { setError(e.message) } finally { setBusy(false) }
    }}><label>Private invitation code<input value={code} onChange={e => setCode(e.target.value)} autoComplete="off" required/></label><button disabled={busy}>Connect securely</button></form> :
      <><Badge>{connection}</Badge>
        {!call && <div className="py-16 text-center text-slate-400">Available · waiting for a call</div>}
        {call?.status === 'ringing' && <div className="text-center py-10"><div className="text-4xl mb-5" aria-hidden="true">☎</div><h2>Incoming AI call</h2><p className="muted mb-6">{call.role_name || 'Information collection assistant'}</p>
          <div className="flex justify-center gap-4"><button disabled={busy} onClick={() => action('accept')}>Accept</button><button className="danger" disabled={busy} onClick={() => action('reject')}>Reject</button></div></div>}
        {call && call.status !== 'ringing' && <div className="mt-6">
          <div className="flex justify-between mb-6"><Badge>{call.status}</Badge><span role="status">{stage}</span></div>
          <p className="rounded-xl bg-slate-950 p-5 leading-relaxed">{call.message || (closed(call) ? 'Call ended.' : 'Preparing AI introduction…')}</p>
          {transcript && <p className="text-sm text-slate-400 mt-3">You said: {transcript}</p>}
          {needsPlay && <button className="mt-4" onClick={async () => { try { setStage('AI speaking'); await player.current.play(); setNeedsPlay(false) } catch { setError('Playback remains blocked. Check browser audio settings.') } }}>Play reply</button>}
          {!closed(call) && <><p className="text-xs text-slate-500 my-4">Audio is processed locally and discarded. Tap Speak, then pause to send (maximum 19 seconds).</p>
            <div className="flex flex-wrap gap-3">
              <button disabled={busy || needsPlay || stage === 'AI speaking' || connection !== 'Connected'} onClick={record}>{stage === 'Listening' ? 'Send turn' : 'Speak'}</button>
              {call.status === 'accepted' && <><button className="secondary" disabled={busy || stage === 'Listening' || stage === 'AI speaking' || needsPlay} onClick={() => action('consent')}>I consent</button><button className="danger" onClick={() => action('refuse')}>Decline consent</button></>}
              {confirming && <button className="secondary" disabled={busy || stage === 'AI speaking' || stage === 'Listening'} onClick={() => action('confirm')}>Confirm details</button>}
              <button className="danger" onClick={() => action('end')}>End call</button>
            </div></>}
          {closed(call) && <p className="text-teal-300 mt-5">This call has ended. Keep the page open for another invitation to call.</p>}
        </div>}
      </>}
  </section></Layout>
}

createRoot(document.getElementById('root')).render(location.pathname === '/receive' ? <Receiver/> : <Dashboard/>)

import { Activity, Eye, EyeOff, Leaf, LogIn, TrafficCone } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { clockSec } from '../lib/format'
import { api } from '../services/api'
import './login.css'

type Tone = 'error' | 'ok' | 'info'
const TONE_CLASS: Record<Tone, string> = {
  error: 'border-crit/60 bg-crit/10 text-[#ffb7b8]',
  ok: 'border-ok/60 bg-ok/10 text-[#9ff0c4]',
  info: 'border-line bg-ink-800/80 text-txt',
}

const field =
  'h-10 w-full border border-line bg-ink-950/80 px-3 text-[14px] text-txt outline-none transition-colors placeholder:text-txt-mute focus:border-sky-accent disabled:opacity-60'

type Backend = 'checking' | 'ok' | 'degraded' | 'offline'

function useBackendStatus(): Backend {
  const [status, setStatus] = useState<Backend>('checking')
  useEffect(() => {
    let alive = true
    const check = () =>
      api
        .get<{ backend: string; database: string }>('/api/health')
        .then((h) => alive && setStatus(h.backend === 'ok' && h.database === 'ok' ? 'ok' : 'degraded'))
        .catch(() => alive && setStatus('offline'))
    check()
    const t = window.setInterval(check, 10000)
    return () => {
      alive = false
      window.clearInterval(t)
    }
  }, [])
  return status
}

function useNow() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])
  return now
}

const STATUS: Record<Backend, { text: string; dot: string }> = {
  checking: { text: 'Connecting...', dot: 'bg-txt-mute' },
  ok: { text: 'Operational', dot: 'bg-ok' },
  degraded: { text: 'Degraded', dot: 'bg-warn' },
  offline: { text: 'Backend offline', dot: 'bg-crit' },
}

export function LoginPage() {
  const { login, accept } = useAuth()
  const backend = useBackendStatus()
  const now = useNow()
  const [user, setUser] = useState('')
  const [pw, setPw] = useState('')
  const [otp, setOtp] = useState('')
  const [mfa, setMfa] = useState(false)
  const [showPw, setShowPw] = useState(false)
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; kind: Tone } | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (!user.trim() || !pw) {
      setMsg({ text: 'Enter your username or email and password.', kind: 'error' })
      return
    }
    if (mfa && otp.replace(/\D/g, '').length !== 6) {
      setMsg({ text: 'Enter the 6-digit code from your authenticator app.', kind: 'error' })
      return
    }
    setBusy(true)
    setMsg(null)
    try {
      const r = await login(user.trim(), pw, remember, mfa ? otp : undefined)
      if (r.mfa_required) {
        setMfa(true)
        setMsg({ text: 'Two-factor authentication is enabled for this account.', kind: 'info' })
        setBusy(false)
        return
      }
      setMsg({ text: 'Signed in. Loading dashboard...', kind: 'ok' })
      window.setTimeout(() => accept(r.user), 400)
    } catch (err) {
      const text =
        err instanceof Error && err.message && !/^(5\d\d|Failed to fetch)/.test(err.message)
          ? err.message
          : 'Cannot reach the processing backend. Check that it is running.'
      setMsg({ text, kind: 'error' })
      setBusy(false)
    }
  }

  const resetMfa = () => {
    setMfa(false)
    setOtp('')
    setMsg(null)
  }

  const st = STATUS[backend]
  const d = new Date(now)

  return (
    <div className="login-root flex h-full flex-col overflow-y-auto">
      {/* Header */}
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-line-soft bg-ink-950/95 px-4">
        <div className="flex items-center gap-3">
          <div className="flex items-baseline gap-1.5 select-none">
            <span className="font-din text-[22px] font-bold italic tracking-wide text-white">SMART TRAFFIC</span>
            <span className="font-din text-[22px] font-bold italic tracking-wide text-sky-accent">ITS</span>
          </div>
          <span className="hidden border-l border-line-soft pl-3 text-[11px] leading-tight text-txt-dim md:block">
            Smart Traffic Management and Intelligent
            <br />
            Transportation System for Lusaka CBD
          </span>
        </div>
        <div className="flex items-center gap-5 text-[12px]">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${st.dot}`} />
            <span className="text-txt-dim">{st.text}</span>
          </div>
          <div className="num hidden text-right leading-tight sm:block">
            <div className="text-[14px] text-white">{clockSec(now / 1000)}</div>
            <div className="text-[10px] text-txt-dim">
              {d.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}
            </div>
          </div>
        </div>
      </header>

      <main className="flex flex-1 items-center px-4 py-10 sm:px-8 lg:px-16">
        <div className="mx-auto grid w-full max-w-6xl items-center gap-10 lg:grid-cols-[1fr_420px] lg:gap-16">
          <section className="flex max-w-xl flex-col gap-10">
            {/* Brand */}
            <div className="border-l-2 border-sky-accent pl-4">
              <div className="font-din text-[40px] font-bold leading-none tracking-wide text-white">Smart</div>
              <div className="font-din text-[40px] font-bold leading-tight tracking-wide text-sky-accent">Traffic System</div>
              <div className="mt-2 text-[12px] font-semibold tracking-[0.22em] text-txt-dim">MONITOR · ANALYSE · OPTIMISE</div>
            </div>

            {/* Headline */}
            <div>
              <h1 className="text-[34px] font-semibold leading-tight text-white sm:text-[42px]">
                Smarter Traffic.
                <br />A Smoother <span className="text-sky-accent">Lusaka.</span>
              </h1>
              <div className="mt-4 h-px w-64 bg-gradient-to-r from-sky-accent to-transparent" />
            </div>

            {/* Capabilities */}
            <ul className="flex flex-col gap-4">
              {(
                [
                  [Activity, 'Real-Time', 'Monitoring'],
                  [TrafficCone, 'Adaptive Traffic', 'Control'],
                  [Leaf, 'Less Congestion,', 'Greener City'],
                ] as const
              ).map(([Icon, a, b]) => (
                <li key={a} className="flex items-center gap-4">
                  <span className="grid h-11 w-11 shrink-0 place-items-center border border-line bg-ink-900/80 text-sky-accent">
                    <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
                  </span>
                  <span className="text-[15px] font-semibold leading-snug text-white">
                    {a}
                    <br />
                    {b}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* Sign-in panel */}
          <form onSubmit={submit} noValidate className="panel panel-corners w-full">
            <div className="panel-head">
              <span>Operator Sign-in</span>
              <span className="text-[11px] font-normal text-txt-dim">Authorised personnel only</span>
            </div>

            <div className="space-y-4 p-5">
              <div>
                <label htmlFor="login-user" className="label">
                  Username or email
                </label>
                <input
                  id="login-user"
                  className={field}
                  type="text"
                  autoComplete="username"
                  autoFocus
                  value={user}
                  onChange={(e) => setUser(e.target.value)}
                  disabled={mfa}
                />
              </div>

              <div>
                <label htmlFor="login-pw" className="label">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="login-pw"
                    className={`${field} pr-11`}
                    type={showPw ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    disabled={mfa}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw((s) => !s)}
                    aria-label={showPw ? 'Hide password' : 'Show password'}
                    className="absolute right-0 top-0 grid h-10 w-10 place-items-center text-txt-dim hover:text-white focus-visible:text-white"
                  >
                    {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {mfa && (
                <div>
                  <label htmlFor="login-otp" className="label">
                    Authentication code
                  </label>
                  <input
                    id="login-otp"
                    className={`${field} num tracking-[0.4em]`}
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    autoFocus
                    maxLength={7}
                    placeholder="000000"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                  />
                </div>
              )}

              <div className="flex items-center justify-between gap-3 text-[13px]">
                <label className="flex cursor-pointer items-center gap-2 text-txt">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={() => setRemember((r) => !r)}
                    className="h-4 w-4 accent-[#1565c0]"
                  />
                  Keep me signed in
                </label>
                {mfa ? (
                  <button type="button" onClick={resetMfa} className="text-sky-accent hover:text-white">
                    Use another account
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      setMsg({ text: 'Passwords are reset by the system administrator. Contact them for a new password.', kind: 'info' })
                    }
                    className="text-sky-accent hover:text-white"
                  >
                    Forgot password?
                  </button>
                )}
              </div>

              {msg && (
                <div role={msg.kind === 'error' ? 'alert' : 'status'} className={`border px-3 py-2 text-[13px] ${TONE_CLASS[msg.kind]}`}>
                  {msg.text}
                </div>
              )}

              <button
                type="submit"
                disabled={busy}
                className="flex h-10 w-full items-center justify-center gap-2 border border-sky-accent/70 bg-[#1565c0] text-[14px] font-semibold tracking-wide text-white transition-colors hover:bg-[#1e78e0] disabled:cursor-progress disabled:opacity-70"
              >
                <LogIn size={16} />
                {busy ? 'Signing in...' : mfa ? 'Verify and sign in' : 'Sign in'}
              </button>
            </div>

            <div className="border-t border-line-soft px-5 py-3 text-[11px] leading-relaxed text-txt-mute">
              Access is logged. Accounts are issued by the system administrator. Two-factor authentication is
              available on request.
            </div>
          </form>
        </div>
      </main>

      <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-line-soft bg-ink-950/95 px-4 py-2 text-[11px] text-txt-mute">
        <span>Lusaka, Zambia · Research and simulation prototype, not connected to live traffic signals</span>
        <span>v1.1</span>
      </footer>
    </div>
  )
}

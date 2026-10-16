import { useEffect, useState, FormEvent } from 'react'
import { checkSetupLink, completeSetup, detailOf, isUnreachable, type MfaChallenge } from '../api/auth'
import AuthCard from '../components/auth/AuthCard'
import MfaSteps from '../components/auth/MfaSteps'

/**
 * One-time link (D20.3): /setup#token=…  The token is in the fragment, so the
 * browser never sends it in a request line, a Referer or a server log.
 * Set a password, then link 2FA — nothing else is open before both.
 * "Invalid or expired" only when the server says so; no answer is "Server
 * unreachable" (spec §8.4 P3) — a new link would not help then.
 */
const UNREACHABLE = 'Server unreachable — try again in a minute'

export default function Setup() {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
  const [email, setEmail] = useState<string | null>(null)
  const [invalid, setInvalid] = useState<string | null>(token ? null : 'This link is invalid or has expired')
  const [unreachable, setUnreachable] = useState(false)
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null)

  useEffect(() => {
    if (!token) return
    checkSetupLink(token)
      .then((r) => setEmail(r.email))
      .catch((err) => isUnreachable(err)
        ? setUnreachable(true)
        : setInvalid(detailOf(err, 'This link is invalid or has expired')))
  }, [token])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (password !== repeat) {
      setError('The two passwords are not the same')
      return
    }
    setBusy(true)
    try {
      const c = await completeSetup(token, password)
      // the link is used up: take it out of the address bar and the history
      window.history.replaceState(null, '', '/setup')
      setChallenge(c)
    } catch (err) {
      setError(isUnreachable(err) ? UNREACHABLE : detailOf(err, 'Could not set the password'))
    } finally {
      setBusy(false)
    }
  }

  if (challenge) {
    return (
      <AuthCard title="Link two-factor authentication">
        <MfaSteps challenge={challenge} />
      </AuthCard>
    )
  }

  if (unreachable) {
    return (
      <AuthCard title="Set up your account">
        <p className="notice-danger" role="alert" data-error="unreachable">{UNREACHABLE}</p>
        <p className="text-sm text-fg-muted mt-3">The link was not checked; it is still valid if it was before.</p>
      </AuthCard>
    )
  }

  if (invalid) {
    return (
      <AuthCard title="Set up your account">
        <p className="notice-danger" role="alert" data-error="invalid">{invalid}</p>
        <p className="text-sm text-fg-muted mt-3">Ask an administrator for a new link.</p>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Set up your account">
      {email === null ? (
        <p className="text-sm text-fg-muted">Checking the link…</p>
      ) : (
        <form onSubmit={submit} className="space-y-4" data-step="setup">
          <p className="text-sm text-fg-muted">
            Account <strong data-setup-email>{email}</strong>. Choose a password (at least 12 characters);
            next you link two-factor authentication.
          </p>
          {error && <p className="notice-danger" role="alert" data-error>{error}</p>}
          <input
            id="new-password"
            type="password"
            className="input"
            autoComplete="new-password"
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={12}
            required
            autoFocus
          />
          <input
            id="repeat-password"
            type="password"
            className="input"
            autoComplete="new-password"
            placeholder="Repeat the password"
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            minLength={12}
            required
          />
          <button type="submit" className="btn-primary w-full py-2.5" disabled={busy}>
            {busy ? 'Saving…' : 'Set password'}
          </button>
        </form>
      )}
    </AuthCard>
  )
}

import { useEffect, useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  confirmEnrolment,
  detailOf,
  getMe,
  startEnrolment,
  verifyMfa,
  type EnrollStart,
  type MfaChallenge,
} from '../../api/auth'
import { useAuthStore, type UserRole } from '../../store/authStore'

/** Store the FULL token (after the second factor) and go in. */
export function useFinishLogin() {
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()
  return async (accessToken: string) => {
    const payload = JSON.parse(atob(accessToken.split('.')[1]))
    const me = await getMe(accessToken)
    setAuth(accessToken, payload.role as UserRole, me.email, payload.marina_ids ?? [], me.full_name)
    navigate('/marinas', { replace: true })
  }
}

function CodeStep({ mfaToken, onDone }: { mfaToken: string; onDone: (t: string) => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const { access_token } = await verifyMfa(mfaToken, code)
      onDone(access_token)
    } catch (err) {
      setError(detailOf(err, 'Invalid code'))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" data-step="mfa-code">
      <p className="text-sm text-gray-600">
        Enter the 6-digit code from your authenticator app, or one of your backup codes.
      </p>
      {error && <p className="text-sm text-red-700" data-error>{error}</p>}
      <input
        id="code"
        name="code"
        className="input text-center tracking-widest text-lg"
        inputMode="text"
        autoComplete="one-time-code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="123456"
        required
        autoFocus
      />
      <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={busy}>
        {busy ? 'Checking…' : 'Verify'}
      </button>
    </form>
  )
}

export function BackupCodesView({ codes, onContinue }: { codes: string[]; onContinue: () => void }) {
  const [saved, setSaved] = useState(false)
  return (
    <div className="space-y-4" data-step="backup-codes">
      <p className="text-sm text-gray-700">
        <strong>Backup codes — shown only now.</strong> Each works once, if the phone is lost.
        Store them somewhere safe, not on the same phone.
      </p>
      <ul className="grid grid-cols-2 gap-2 font-mono text-sm bg-gray-50 border rounded-lg p-3">
        {codes.map((c) => (
          <li key={c} data-backup-code>{c}</li>
        ))}
      </ul>
      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        I have stored these codes
      </label>
      <button className="btn-primary w-full justify-center py-2.5" disabled={!saved} onClick={onContinue}>
        Continue
      </button>
    </div>
  )
}

function EnrollStep({ mfaToken, onDone }: {
  mfaToken: string
  onDone: (token: string, codes: string[]) => void
}) {
  const [data, setData] = useState<EnrollStart | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    startEnrolment(mfaToken)
      .then(setData)
      .catch((err) => setError(detailOf(err, 'Could not start linking two-factor authentication')))
  }, [mfaToken])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const r = await confirmEnrolment(mfaToken, code)
      onDone(r.access_token, r.backup_codes)
    } catch (err) {
      setError(detailOf(err, 'Invalid code'))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4" data-step="mfa-enroll">
      <p className="text-sm text-gray-600">
        Two-factor authentication is required. Scan the code with an authenticator app
        (Google Authenticator, Microsoft Authenticator, Aegis, 1Password…) and enter the code it shows.
      </p>
      {error && <p className="text-sm text-red-700" data-error>{error}</p>}
      {data && (
        <>
          <img
            className="mx-auto w-48 h-48"
            alt="QR code for the authenticator app"
            src={`data:image/svg+xml;utf8,${encodeURIComponent(data.qr_svg)}`}
          />
          <p className="text-xs text-gray-500 text-center">
            Cannot scan? Type this key: <code className="font-mono break-all" data-totp-secret>{data.secret}</code>
          </p>
          <form onSubmit={submit} className="space-y-3">
            <input
              id="code"
              name="code"
              className="input text-center tracking-widest text-lg"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              required
            />
            <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={busy}>
              {busy ? 'Checking…' : 'Link and sign in'}
            </button>
          </form>
        </>
      )}
    </div>
  )
}

/** Everything after a correct password: the code, or linking 2FA first. */
export default function MfaSteps({ challenge }: { challenge: MfaChallenge }) {
  const finish = useFinishLogin()
  const [codes, setCodes] = useState<{ token: string; codes: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const done = (token: string) => finish(token).catch(() => setError('Sign-in failed, try again.'))

  if (error) return <p className="text-sm text-red-700">{error}</p>
  if (codes) return <BackupCodesView codes={codes.codes} onContinue={() => done(codes.token)} />
  if (challenge.mfa_enrolled) return <CodeStep mfaToken={challenge.mfa_token} onDone={done} />
  return (
    <EnrollStep
      mfaToken={challenge.mfa_token}
      onDone={(token, backup) => setCodes({ token, codes: backup })}
    />
  )
}

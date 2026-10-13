import { useEffect, useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, detailOf, type MfaChallenge } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import AuthCard from '../components/auth/AuthCard'
import MfaSteps from '../components/auth/MfaSteps'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null)
  const { isAuthenticated } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    if (isAuthenticated) navigate('/marinas', { replace: true })
  }, [isAuthenticated, navigate])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      setChallenge(await login({ email, password }))
      setPassword('')
    } catch (err: unknown) {
      setError(detailOf(err, 'Login failed. Please check your credentials.'))
    } finally {
      setLoading(false)
    }
  }

  if (challenge) {
    return (
      <AuthCard title={challenge.mfa_enrolled ? 'Two-factor authentication' : 'Link two-factor authentication'}>
        <MfaSteps challenge={challenge} />
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Sign in to your account">
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
            Email address
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            placeholder="you@marina.com"
            required
            autoFocus
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input"
            placeholder="••••••••"
            required
          />
        </div>

        <button type="submit" className="btn-primary w-full justify-center py-2.5" disabled={loading}>
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </AuthCard>
  )
}

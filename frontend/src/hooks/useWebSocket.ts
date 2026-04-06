import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../store/authStore'

const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

export interface WebhookEvent {
  event: string
  data: {
    marina_id: number
    event_type: string
    payload: Record<string, unknown>
    timestamp: string
  }
}

interface UseWebSocketOptions {
  marinaId?: number
  onMessage?: (msg: WebhookEvent) => void
}

export function useWebSocket(options: UseWebSocketOptions = {}) {
  const { marinaId, onMessage } = options
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef(0)
  const [wsConnected, setWsConnected] = useState(false)

  const { token } = useAuthStore()

  useEffect(() => {
    function connect() {
      const params = new URLSearchParams()
      if (token) params.set('token', token)
      if (marinaId != null) params.set('marina_id', String(marinaId))
      const url = `${WS_BASE}?${params.toString()}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setWsConnected(true)
        attemptRef.current = 0
        // Heartbeat ping every 20s
        const ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, 20_000)
        ;(ws as WebSocket & { _pingInterval?: ReturnType<typeof setInterval> })._pingInterval = ping
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WebhookEvent
          onMessage?.(msg)
        } catch {
          // pong or unknown text
        }
      }

      ws.onclose = () => {
        setWsConnected(false)
        clearInterval(
          (ws as WebSocket & { _pingInterval?: ReturnType<typeof setInterval> })._pingInterval
        )
        const delay = Math.min(1000 * Math.pow(2, attemptRef.current), 30_000)
        attemptRef.current += 1
        reconnectTimer.current = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marinaId, token])

  return { wsConnected }
}

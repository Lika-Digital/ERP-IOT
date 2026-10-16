import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getAlarmLog, acknowledgeAlarm, type AlarmLogEntry } from '../api/alarms'
import ConfirmDialog from '../components/ui/ConfirmDialog'
import Status, { ALARM_STATE } from '../components/ui/Status'
import { dateTime } from '../utils/format'

export default function Alarms() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)

  const [alarms, setAlarms] = useState<AlarmLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [unackOnly, setUnackOnly] = useState(false)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [ackDialog, setAckDialog] = useState<{ alarmId: number; pedestalId: number } | null>(null)

  const fetchAlarms = useCallback(async () => {
    try {
      setLoading(true)
      const resp = await getAlarmLog(id, { limit: 200, unacknowledged_only: unackOnly })
      setAlarms(resp.alarms)
      setError(null)
    } catch {
      setError('Failed to load the alarm log.')
    } finally {
      setLoading(false)
    }
  }, [id, unackOnly])

  useEffect(() => {
    fetchAlarms()
  }, [fetchAlarms])

  const handleAcknowledge = async () => {
    if (!ackDialog) return
    setActionLoading(ackDialog.alarmId)
    try {
      await acknowledgeAlarm(id, ackDialog.alarmId, ackDialog.pedestalId)
      setAckDialog(null)
      await fetchAlarms()
    } catch {
      setError('Failed to acknowledge the alarm.')
    } finally {
      setActionLoading(null)
    }
  }

  const alarmType = (entry: AlarmLogEntry): string => {
    const d = entry.alarm_data
    return String(d.alarm_type ?? d.event_type ?? d.type ?? 'unknown')
  }

  return (
    <div className="page max-w-5xl" data-page="alarms">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="page-title">Alarm log</h1>
          <p className="page-lead">Alarms reported by the cabinets, newest first</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-fg-muted cursor-pointer">
            <input type="checkbox" checked={unackOnly} onChange={(e) => setUnackOnly(e.target.checked)} />
            Unacknowledged only
          </label>
          <button onClick={fetchAlarms} className="btn-secondary" disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && <div className="notice-danger mb-4" role="alert">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-fg" />
        </div>
      ) : alarms.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-fg-muted">{unackOnly ? 'No unacknowledged alarms.' : 'No alarms recorded.'}</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {alarms.map((alarm) => {
            const st = ALARM_STATE[alarm.acknowledged_at ? 'acknowledged' : 'open']
            return (
              <li
                key={alarm.id}
                className={`card !p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-l-4 ${
                  alarm.acknowledged_at ? 'border-l-st-grey-line' : 'border-l-st-red-line'
                }`}
                data-alarm-log={alarm.id}
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Status tone={st.tone} icon={st.icon} word={st.word} />
                    <span className="font-semibold">{alarmType(alarm)}</span>
                    <span className="text-xs text-fg-muted">Pedestal {alarm.pedestal_id}</span>
                  </div>
                  <p className="text-xs text-fg-muted">Received {dateTime(alarm.received_at)}</p>
                  {alarm.acknowledged_at && (
                    <p className="text-xs text-fg-muted">
                      Acknowledged {dateTime(alarm.acknowledged_at)}
                    </p>
                  )}
                  {alarm.alarm_data.value != null && (
                    <p className="text-xs text-fg-muted">Value: {String(alarm.alarm_data.value)}</p>
                  )}
                </div>

                {!alarm.acknowledged_at && (
                  <button
                    onClick={() => setAckDialog({ alarmId: alarm.id, pedestalId: alarm.pedestal_id })}
                    className="btn-primary btn-sm shrink-0 self-start sm:self-center"
                    disabled={actionLoading === alarm.id}
                  >
                    Acknowledge
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <ConfirmDialog
        isOpen={!!ackDialog}
        title="Acknowledge alarm"
        message={`Acknowledge alarm #${ackDialog?.alarmId}?`}
        confirmLabel="Acknowledge"
        onConfirm={handleAcknowledge}
        onCancel={() => setAckDialog(null)}
      />
    </div>
  )
}

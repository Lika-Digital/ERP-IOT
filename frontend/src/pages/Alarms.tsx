import { useEffect, useState, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { getAlarmLog, acknowledgeAlarm, type AlarmLogEntry } from '../api/alarms'
import ConfirmDialog from '../components/ui/ConfirmDialog'

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
      setError('Failed to load alarm log.')
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
      setError('Failed to acknowledge alarm.')
    } finally {
      setActionLoading(null)
    }
  }

  const alarmType = (entry: AlarmLogEntry): string => {
    const d = entry.alarm_data
    return String(d.alarm_type ?? d.event_type ?? d.type ?? 'unknown')
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Alarm Log</h1>
          <p className="text-sm text-gray-500 mt-1">Historical and active alarms</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={unackOnly}
              onChange={(e) => setUnackOnly(e.target.checked)}
              className="rounded"
            />
            Unacknowledged only
          </label>
          <button onClick={fetchAlarms} className="btn-secondary" disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
        </div>
      ) : alarms.length === 0 ? (
        <div className="card text-center py-12">
          <p className="text-gray-400">
            {unackOnly ? 'No unacknowledged alarms.' : 'No alarms recorded.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {alarms.map((alarm) => (
            <div
              key={alarm.id}
              className={`card flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 ${
                alarm.acknowledged_at ? 'opacity-60' : 'border-red-200 bg-red-50'
              }`}
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={alarm.acknowledged_at ? 'badge-gray' : 'badge-red'}>
                    {alarm.acknowledged_at ? 'acknowledged' : 'active'}
                  </span>
                  <span className="text-sm font-medium">{alarmType(alarm)}</span>
                  <span className="text-xs text-gray-400">Pedestal {alarm.pedestal_id}</span>
                </div>
                <p className="text-xs text-gray-500">
                  Received: {new Date(alarm.received_at).toLocaleString()}
                </p>
                {alarm.acknowledged_at && (
                  <p className="text-xs text-gray-400">
                    Acked: {new Date(alarm.acknowledged_at).toLocaleString()}
                  </p>
                )}
                {/* Show key alarm data fields */}
                {alarm.alarm_data.value != null && (
                  <p className="text-xs text-gray-500 mt-1">
                    Value: {String(alarm.alarm_data.value)}
                  </p>
                )}
              </div>

              {!alarm.acknowledged_at && (
                <button
                  onClick={() => setAckDialog({ alarmId: alarm.id, pedestalId: alarm.pedestal_id })}
                  className="btn-secondary text-xs py-1.5 shrink-0"
                  disabled={actionLoading === alarm.id}
                >
                  Acknowledge
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        isOpen={!!ackDialog}
        title="Acknowledge Alarm"
        message={`Are you sure you want to acknowledge alarm #${ackDialog?.alarmId}?`}
        confirmLabel="Acknowledge"
        onConfirm={handleAcknowledge}
        onCancel={() => setAckDialog(null)}
      />
    </div>
  )
}

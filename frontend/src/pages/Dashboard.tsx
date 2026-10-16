/**
 * Main dashboard (D23, spec §6.6): the map, three cards, Needs attention, Cabinets —
 * all from the database, nothing live from a cabinet. The live cabinet cards that were
 * below until 6a are on Pedestal control now (6b).
 */
import { useParams } from 'react-router-dom'
import DashboardOverview from '../components/DashboardOverview'
import { useMarinaName } from '../hooks/useMarinaName'

export default function Dashboard() {
  const { marinaId } = useParams<{ marinaId: string }>()
  const id = Number(marinaId)
  const name = useMarinaName(id)

  return (
    <div className="page" data-page="dashboard">
      <div className="mb-6">
        <h1 className="page-title">{name ?? 'Dashboard'}</h1>
        <p className="page-lead">The marina as the collector last saw it</p>
      </div>
      <DashboardOverview marinaId={id} />
    </div>
  )
}

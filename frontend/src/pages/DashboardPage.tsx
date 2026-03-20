import { useDashboard } from '@/hooks/useDashboard'
import ActivityFeed from '@/components/dashboard/ActivityFeed'
import ConnectorStatusPanel from '@/components/dashboard/ConnectorStatusPanel'
import GraphMiniView from '@/components/dashboard/GraphMiniView'
import KnowledgeBaseStats from '@/components/dashboard/KnowledgeBaseStats'
import UpcomingItems from '@/components/dashboard/UpcomingItems'

export default function DashboardPage() {
  const { activity, stats, connectors, upcoming, isLoading, triggerSync, isSyncing } =
    useDashboard()

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <h1 className="sr-only">Dashboard</h1>
      <KnowledgeBaseStats stats={stats} isLoading={isLoading} />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <ActivityFeed items={activity} isLoading={isLoading} />
        <ConnectorStatusPanel
          connectors={connectors}
          isLoading={isLoading}
          onSync={triggerSync}
          isSyncing={isSyncing}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <UpcomingItems items={upcoming} isLoading={isLoading} />
        <GraphMiniView />
      </div>
    </div>
  )
}

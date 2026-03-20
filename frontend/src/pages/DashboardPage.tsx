import { useDashboard } from '@/hooks/useDashboard'
import ActivityFeed from '@/components/dashboard/ActivityFeed'
import ConnectorStatusPanel from '@/components/dashboard/ConnectorStatusPanel'
import GraphMiniView from '@/components/dashboard/GraphMiniView'
import KnowledgeBaseStats from '@/components/dashboard/KnowledgeBaseStats'
import UpcomingItems from '@/components/dashboard/UpcomingItems'

export default function DashboardPage() {
  const {
    activity,
    stats,
    connectors,
    upcoming,
    isLoadingActivity,
    isLoadingStats,
    isLoadingConnectors,
    isLoadingUpcoming,
    errors,
    triggerSync,
    isSyncing,
    syncError,
  } = useDashboard()

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <h1 className="sr-only">Dashboard</h1>

      {syncError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Sync failed: {syncError.message}
        </div>
      )}

      {errors.stats && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          Failed to load stats: {errors.stats.message}
        </div>
      )}

      <KnowledgeBaseStats stats={stats} isLoading={isLoadingStats} />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-2">
        <ActivityFeed items={activity} isLoading={isLoadingActivity} />
        <ConnectorStatusPanel
          connectors={connectors}
          isLoading={isLoadingConnectors}
          onSync={triggerSync}
          isSyncing={isSyncing}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <UpcomingItems items={upcoming} isLoading={isLoadingUpcoming} />
        <GraphMiniView />
      </div>
    </div>
  )
}

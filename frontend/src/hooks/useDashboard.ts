import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchConnectorStatuses,
  fetchDashboardActivity,
  fetchDashboardStats,
  fetchDashboardUpcoming,
  triggerConnectorSync,
} from '@/services/api'

export function useDashboard() {
  const queryClient = useQueryClient()

  const activityQuery = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: fetchDashboardActivity,
    refetchInterval: 30_000,
  })

  const statsQuery = useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: fetchDashboardStats,
    refetchInterval: 60_000,
  })

  const connectorsQuery = useQuery({
    queryKey: ['connectors-status'],
    queryFn: fetchConnectorStatuses,
    refetchInterval: 30_000,
  })

  const upcomingQuery = useQuery({
    queryKey: ['dashboard-upcoming'],
    queryFn: fetchDashboardUpcoming,
    staleTime: 5 * 60_000,
  })

  const syncMutation = useMutation({
    mutationFn: triggerConnectorSync,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['connectors-status'] })
    },
  })

  const isLoading =
    activityQuery.isLoading ||
    statsQuery.isLoading ||
    connectorsQuery.isLoading ||
    upcomingQuery.isLoading

  return {
    activity: activityQuery.data?.items ?? [],
    stats: statsQuery.data ?? null,
    connectors: connectorsQuery.data ?? [],
    upcoming: upcomingQuery.data?.items ?? [],
    isLoading,
    errors: {
      activity: activityQuery.error,
      stats: statsQuery.error,
      connectors: connectorsQuery.error,
      upcoming: upcomingQuery.error,
    },
    triggerSync: syncMutation.mutate,
    isSyncing: syncMutation.isPending,
  }
}

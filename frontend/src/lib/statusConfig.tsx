import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle, XCircle } from 'lucide-react'

export type StatusLevel = 'healthy' | 'degraded' | 'unavailable'

export const STATUS_CONFIG: Record<StatusLevel, { icon: ReactNode; badge: string }> = {
  healthy: {
    icon: <CheckCircle className="size-4 text-green-500" />,
    badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  degraded: {
    icon: <AlertCircle className="size-4 text-yellow-500" />,
    badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  unavailable: {
    icon: <XCircle className="size-4 text-red-500" />,
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
}

import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorFallback } from '@/components/layout/ErrorFallback'
import DashboardPage from '@/pages/DashboardPage'
import ChatPage from '@/pages/ChatPage'
import SearchPage from '@/pages/SearchPage'
import SettingsPage from '@/pages/SettingsPage'
import NotFoundPage from '@/pages/NotFoundPage'

// Lazy-load GraphPage so react-force-graph (which accesses the AFRAME global at
// module-load time) is not imported until the user navigates to /graph.
const GraphPage = lazy(() => import('@/pages/GraphPage'))

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    errorElement: <ErrorFallback />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'graph', element: <Suspense fallback={null}><GraphPage /></Suspense> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

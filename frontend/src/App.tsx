import type React from 'react'
import { useHashRoute, type PageId } from './hooks/useHashRoute'
import { LiveDataProvider } from './hooks/useLiveData'
import { AppLayout } from './layouts/AppLayout'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { CameraManagementPage } from './pages/CameraManagementPage'
import { CongestionPage } from './pages/CongestionPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { IncidentsPage } from './pages/IncidentsPage'
import { LiveMonitoringPage } from './pages/LiveMonitoringPage'
import { OverviewPage } from './pages/OverviewPage'
import { PriorityPage } from './pages/PriorityPage'
import { SettingsPage } from './pages/SettingsPage'
import { SimulationPage } from './pages/SimulationPage'
import { SurveysPage } from './pages/SurveysPage'

export default function App() {
  const [page, navigate] = useHashRoute()
  const pages: Record<PageId, React.ReactNode> = {
    overview: <OverviewPage onNavigate={navigate} />,
    live: <LiveMonitoringPage />,
    cameras: <CameraManagementPage />,
    analytics: <AnalyticsPage />,
    congestion: <CongestionPage />,
    priority: <PriorityPage />,
    simulation: <SimulationPage />,
    evaluation: <EvaluationPage />,
    incidents: <IncidentsPage />,
    surveys: <SurveysPage />,
    settings: <SettingsPage />,
  }
  return (
    <LiveDataProvider>
      <AppLayout page={page} onNavigate={navigate}>
        {pages[page]}
      </AppLayout>
    </LiveDataProvider>
  )
}

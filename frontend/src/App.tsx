
import React, { Suspense } from 'react'
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ChatPage from './pages/ChatPage'
import ErrorBoundary from './components/ErrorBoundary'

const AnalysisPage = React.lazy(() => import('./pages/AnalysisPage'))
const ResultsPage = React.lazy(() => import('./pages/ResultsPage'))
const SkillsPage = React.lazy(() => import('./pages/SkillsPage'))
const DatasetsPage = React.lazy(() => import('./pages/DatasetsPage'))
const HistoryPage = React.lazy(() => import('./pages/HistoryPage'))
const SettingsPage = React.lazy(() => import('./pages/SettingsPage'))

function PageLoader() {
  return (
    <div className="flex-1 flex items-center justify-center bg-stone-50">
      <div className="flex flex-col items-center gap-3">
        <div className="w-5 h-5 border-2 border-stone-300 border-t-stone-600 rounded-full animate-spin" />
        <span className="text-sm text-stone-400">加载中...</span>
      </div>
    </div>
  )
}

function PageErrorFallback() {
  return (
    <div className="flex-1 flex items-center justify-center bg-stone-50">
      <div className="text-center space-y-3">
        <p className="text-stone-500 text-sm">页面加载出错</p>
        <button
          onClick={() => window.location.reload()}
          className="px-3 py-1.5 text-sm bg-stone-200 text-stone-700 rounded hover:bg-stone-300 transition-colors"
        >
          刷新页面
        </button>
      </div>
    </div>
  )
}

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={
              <ErrorBoundary fallback={<PageErrorFallback />}>
                <ChatPage />
              </ErrorBoundary>
            } />
            <Route path="analysis" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><AnalysisPage /></Suspense></ErrorBoundary>} />
            <Route path="results" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><ResultsPage /></Suspense></ErrorBoundary>} />
            <Route path="skills" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><SkillsPage /></Suspense></ErrorBoundary>} />
            <Route path="datasets" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><DatasetsPage /></Suspense></ErrorBoundary>} />
            <Route path="history" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><HistoryPage /></Suspense></ErrorBoundary>} />
            <Route path="settings" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><SettingsPage /></Suspense></ErrorBoundary>} />
          </Route>
        </Routes>
      </Router>
    </ErrorBoundary>
  )
}

export default App

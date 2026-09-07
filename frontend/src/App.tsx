
import React, { Suspense, type ReactNode } from 'react'
import { BrowserRouter as Router, Navigate, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ErrorBoundary from './components/ErrorBoundary'
import { AppProvider } from './context/AppContext'
import { useAppContext } from './context/AppContext'
import LoginModal from './components/LoginModal'
import { buildUrl, getApiKey, getJwtToken } from './services/api'
import { DEFAULT_PRODUCT_PATH, hasProductAccess, YIELD_ESTIMATE_PATH } from './productRoutes'

const AnalysisPage = React.lazy(() => import('./pages/AnalysisPage'))
const ChatPage = React.lazy(() => import('./pages/ChatPage'))
const ResultsPage = React.lazy(() => import('./pages/ResultsPage'))
const SkillsPage = React.lazy(() => import('./pages/SkillsPage'))
const DatasetsPage = React.lazy(() => import('./pages/DatasetsPage'))
const KnowledgePage = React.lazy(() => import('./pages/KnowledgePage'))
const ImageAnalysisPage = React.lazy(() => import('./pages/ImageAnalysisPage'))
const BatchAnalysisPage = React.lazy(() => import('./pages/BatchAnalysisPage'))
const HistoryPage = React.lazy(() => import('./pages/HistoryPage'))
const SettingsPage = React.lazy(() => import('./pages/SettingsPage'))
const MapWorkspaceDemoPage = React.lazy(() => import('./pages/MapWorkspaceDemoPage'))
const YieldEstimatePage = React.lazy(() => import('./pages/YieldEstimatePage'))

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

function ProductAccessGate({ children }: { children: ReactNode }) {
  const { state, login, register, logout } = useAppContext()
  const authenticated = hasProductAccess(state.auth.isAuthenticated, getApiKey())
  if (authenticated) return <div onClickCapture={handleArtifactNavigation}>
    <div className="fixed right-4 top-4 z-[1000] flex items-center gap-2 rounded-full bg-slate-950/85 px-3 py-1.5 text-xs text-slate-100 shadow-lg backdrop-blur">
      <span className="h-2 w-2 rounded-full bg-emerald-400" />
      <span>已登录</span>
      <button
        type="button"
        className="text-slate-300 underline underline-offset-2 hover:text-white"
        onClick={logout}
      >退出</button>
    </div>
    {children}
  </div>
  return <div className="grid min-h-screen place-items-center bg-[#071611] text-slate-100">
    <div className="max-w-sm px-6 text-center">
      <p className="text-xs font-semibold tracking-[0.2em] text-emerald-300">KTP AGRICULTURE INTELLIGENCE</p>
      <h1 className="mt-3 text-2xl font-semibold">登录后进入地图分析工作台</h1>
      <p className="mt-2 text-sm text-slate-400">农场、选片、LAI 反演和结果图层将在同一工作空间中完成。</p>
    </div>
    <LoginModal isOpen onClose={() => undefined} onLogin={login} onRegister={register} />
  </div>
}

async function handleArtifactNavigation(event: React.MouseEvent<HTMLDivElement>) {
  const anchor = (event.target as HTMLElement).closest('a[href*="/api/product/v1/artifacts/"]') as HTMLAnchorElement | null
  if (!anchor) return
  event.preventDefault()
  const popup = anchor.target === '_blank' ? window.open('', '_blank') : null
  if (popup) popup.opener = null
  try {
    const token = getJwtToken() || getApiKey()
    const response = await fetch(buildUrl(anchor.getAttribute('href') || ''), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    if (!response.ok) throw new Error(`Artifact request failed: ${response.status}`)
    const objectUrl = URL.createObjectURL(await response.blob())
    if (anchor.hasAttribute('download')) {
      const download = document.createElement('a')
      download.href = objectUrl
      download.download = anchor.getAttribute('download') || ''
      download.click()
    } else if (popup) {
      popup.location.href = objectUrl
    } else {
      window.open(objectUrl, '_blank', 'noopener')
    }
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  } catch (error) {
    popup?.close()
    window.alert(error instanceof Error ? error.message : '无法读取受保护的 Artifact')
  }
}

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <AppProvider>
          <Routes>
            <Route path="/" element={<Navigate to={DEFAULT_PRODUCT_PATH} replace />} />
            <Route path="/workspace-demo" element={<Navigate to="/workspace" replace />} />
            <Route path="/workspace" element={<ProductAccessGate><Suspense fallback={<PageLoader />}><MapWorkspaceDemoPage live /></Suspense></ProductAccessGate>} />
            <Route path="/map" element={<Navigate to="/workspace" replace />} />
            <Route element={<ProductAccessGate><Layout /></ProductAccessGate>}>
            <Route path="/chat" element={
              <ErrorBoundary fallback={<PageErrorFallback />}>
                <Suspense fallback={<PageLoader />}><ChatPage /></Suspense>
              </ErrorBoundary>
            } />
            <Route path="analysis" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><AnalysisPage /></Suspense></ErrorBoundary>} />
            <Route path={YIELD_ESTIMATE_PATH} element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><YieldEstimatePage /></Suspense></ErrorBoundary>} />
            <Route path="results" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><ResultsPage /></Suspense></ErrorBoundary>} />
            <Route path="skills" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><SkillsPage /></Suspense></ErrorBoundary>} />
            <Route path="datasets" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><DatasetsPage /></Suspense></ErrorBoundary>} />
            <Route path="image-analysis" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><ImageAnalysisPage /></Suspense></ErrorBoundary>} />
            <Route path="batch-analysis" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><BatchAnalysisPage /></Suspense></ErrorBoundary>} />
            <Route path="knowledge" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><KnowledgePage /></Suspense></ErrorBoundary>} />
            <Route path="history" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><HistoryPage /></Suspense></ErrorBoundary>} />
            <Route path="settings" element={<ErrorBoundary fallback={<PageErrorFallback />}><Suspense fallback={<PageLoader />}><SettingsPage /></Suspense></ErrorBoundary>} />
            </Route>
            <Route path="*" element={<Navigate to={DEFAULT_PRODUCT_PATH} replace />} />
          </Routes>
        </AppProvider>
      </Router>
    </ErrorBoundary>
  )
}

export default App

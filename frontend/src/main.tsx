import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { installChunkLoadRecovery } from './utils/chunkLoadRecovery'

installChunkLoadRecovery()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)

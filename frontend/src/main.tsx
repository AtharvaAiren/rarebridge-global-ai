import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/fonts.ts'
import './styles/token.css'
import './styles/app.css'
import './styles/graph.css'
import './styles/route.css'
import './styles/evidence.css'
import './styles/brief.css'
import './styles/research.css'
import { ApiProvider } from './api/ApiContext.tsx'
import { apiClient } from './api/index.ts'
import { App } from './App.tsx'

const rootElement = document.getElementById('root')
if (!rootElement) throw new Error('Missing #root element in index.html.')

createRoot(rootElement).render(
  <StrictMode>
    <ApiProvider client={apiClient}>
      <App />
    </ApiProvider>
  </StrictMode>,
)

import { Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { SearchPage } from './pages/SearchPage'
import { CompanyDetailPage } from './pages/CompanyDetailPage'
import { PersonDetailPage } from './pages/PersonDetailPage'
import { ImportPage } from './pages/ImportPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/search" replace />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/companies/:id" element={<CompanyDetailPage />} />
        <Route path="/persons/:id" element={<PersonDetailPage />} />
        <Route path="/import" element={<ImportPage />} />
      </Routes>
    </Layout>
  )
}

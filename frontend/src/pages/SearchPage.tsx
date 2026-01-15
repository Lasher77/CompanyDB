import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, Building2, User, MapPin, FileText, ChevronRight, Filter, ChevronDown, X, Users, Euro } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Pagination, PaginationInfo } from '@/components/ui/pagination'
import { companiesApi, personsApi } from '@/lib/api'
import { cn, getStatusColor } from '@/lib/utils'
import type { CompanyListItem, PersonListItem } from '@/types'

type SearchType = 'companies' | 'persons'

const ITEMS_PER_PAGE = 20

interface Filters {
  city: string
  postalCode: string
  employeeMin: string
  employeeMax: string
  revenueMin: string
  revenueMax: string
}

const defaultFilters: Filters = {
  city: '',
  postalCode: '',
  employeeMin: '',
  employeeMax: '',
  revenueMin: '',
  revenueMax: '',
}

export function SearchPage() {
  const navigate = useNavigate()
  const [searchType, setSearchType] = useState<SearchType>('companies')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [filters, setFilters] = useState<Filters>(defaultFilters)
  const [showFilters, setShowFilters] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [companies, setCompanies] = useState<CompanyListItem[]>([])
  const [persons, setPersons] = useState<PersonListItem[]>([])
  const [total, setTotal] = useState(0)
  const [hasSearched, setHasSearched] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)

  const activeFilterCount = Object.values(filters).filter(v => v !== '').length

  const handleSearch = useCallback(async (page: number = 1) => {
    if (!query.trim()) return

    setIsLoading(true)
    setHasSearched(true)
    setCurrentPage(page)

    const offset = (page - 1) * ITEMS_PER_PAGE

    try {
      if (searchType === 'companies') {
        const result = await companiesApi.search({
          q: query,
          status: statusFilter || undefined,
          city: filters.city || undefined,
          postal_code: filters.postalCode || undefined,
          employee_min: filters.employeeMin ? parseInt(filters.employeeMin) : undefined,
          employee_max: filters.employeeMax ? parseInt(filters.employeeMax) : undefined,
          revenue_min: filters.revenueMin ? parseFloat(filters.revenueMin) : undefined,
          revenue_max: filters.revenueMax ? parseFloat(filters.revenueMax) : undefined,
          limit: ITEMS_PER_PAGE,
          offset,
        })
        setCompanies(result.items)
        setPersons([])
        setTotal(result.total)
      } else {
        const result = await personsApi.search({
          q: query,
          city: filters.city || undefined,
          limit: ITEMS_PER_PAGE,
          offset,
        })
        setPersons(result.items)
        setCompanies([])
        setTotal(result.total)
      }
    } catch (error) {
      console.error('Search error:', error)
    } finally {
      setIsLoading(false)
    }
  }, [query, searchType, statusFilter, filters])

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE)

  const handlePageChange = (page: number) => {
    handleSearch(page)
    // Scroll to top of results
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const clearFilters = () => {
    setFilters(defaultFilters)
  }

  const updateFilter = (key: keyof Filters, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch(1)
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl font-semibold text-gray-900">
          Firmen & Personen suchen
        </h1>
        <p className="mt-2 text-gray-600">
          Durchsuchen Sie die NorthData-Datenbank
        </p>
      </div>

      {/* Search Card */}
      <Card className="mx-auto max-w-2xl">
        <CardContent className="p-6">
          {/* Search Type Toggle */}
          <div className="mb-4 flex justify-center">
            <div className="inline-flex rounded-lg bg-gray-100 p-1">
              <button
                onClick={() => setSearchType('companies')}
                className={cn(
                  'flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all',
                  searchType === 'companies'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                )}
              >
                <Building2 className="h-4 w-4" />
                Firmen
              </button>
              <button
                onClick={() => setSearchType('persons')}
                className={cn(
                  'flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all',
                  searchType === 'persons'
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                )}
              >
                <User className="h-4 w-4" />
                Personen
              </button>
            </div>
          </div>

          {/* Search Input */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <Input
                type="text"
                placeholder={
                  searchType === 'companies'
                    ? 'Firmenname, Register-ID oder Stadt...'
                    : 'Vor- oder Nachname...'
                }
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                className="pl-10"
              />
            </div>
            <Button onClick={() => handleSearch(1)} disabled={isLoading || !query.trim()}>
              {isLoading ? 'Suche...' : 'Suchen'}
            </Button>
          </div>

          {/* Filter Toggle Button */}
          {searchType === 'companies' && (
            <div className="mt-4">
              <button
                onClick={() => setShowFilters(!showFilters)}
                className={cn(
                  'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  showFilters || activeFilterCount > 0
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                <Filter className="h-4 w-4" />
                Filter
                {activeFilterCount > 0 && (
                  <Badge className="ml-1 bg-blue-600 text-white text-xs px-1.5 py-0.5">
                    {activeFilterCount}
                  </Badge>
                )}
                <ChevronDown className={cn(
                  'h-4 w-4 transition-transform',
                  showFilters && 'rotate-180'
                )} />
              </button>
            </div>
          )}

          {/* Advanced Filters Panel */}
          <AnimatePresence>
            {showFilters && searchType === 'companies' && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="overflow-hidden"
              >
                <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-medium text-gray-700">Erweiterte Filter</h3>
                    {activeFilterCount > 0 && (
                      <button
                        onClick={clearFilters}
                        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700"
                      >
                        <X className="h-3 w-3" />
                        Filter zurücksetzen
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Location Filters */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        Standort
                      </h4>
                      <div className="space-y-2">
                        <Input
                          type="text"
                          placeholder="Stadt"
                          value={filters.city}
                          onChange={(e) => updateFilter('city', e.target.value)}
                          className="h-9 text-sm"
                        />
                        <Input
                          type="text"
                          placeholder="Postleitzahl"
                          value={filters.postalCode}
                          onChange={(e) => updateFilter('postalCode', e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                    </div>

                    {/* Employee Filter */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        Mitarbeiter
                      </h4>
                      <div className="flex gap-2">
                        <Input
                          type="number"
                          placeholder="Min"
                          min="0"
                          value={filters.employeeMin}
                          onChange={(e) => updateFilter('employeeMin', e.target.value)}
                          className="h-9 text-sm"
                        />
                        <span className="flex items-center text-gray-400">-</span>
                        <Input
                          type="number"
                          placeholder="Max"
                          min="0"
                          value={filters.employeeMax}
                          onChange={(e) => updateFilter('employeeMax', e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                    </div>

                    {/* Revenue Filter */}
                    <div className="space-y-3 md:col-span-2">
                      <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide flex items-center gap-1">
                        <Euro className="h-3 w-3" />
                        Umsatz (EUR)
                      </h4>
                      <div className="flex gap-2 max-w-md">
                        <Input
                          type="number"
                          placeholder="Min"
                          min="0"
                          value={filters.revenueMin}
                          onChange={(e) => updateFilter('revenueMin', e.target.value)}
                          className="h-9 text-sm"
                        />
                        <span className="flex items-center text-gray-400">-</span>
                        <Input
                          type="number"
                          placeholder="Max"
                          min="0"
                          value={filters.revenueMax}
                          onChange={(e) => updateFilter('revenueMax', e.target.value)}
                          className="h-9 text-sm"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Status Filters (only for companies) */}
          {searchType === 'companies' && (
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="text-sm text-gray-500">Status:</span>
              {['', 'active', 'terminated', 'liquidation'].map((status) => (
                <button
                  key={status}
                  onClick={() => setStatusFilter(status)}
                  className={cn(
                    'rounded-full px-3 py-1 text-xs font-medium transition-colors',
                    statusFilter === status
                      ? 'bg-gray-900 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  )}
                >
                  {status || 'Alle'}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      <AnimatePresence mode="wait">
        {isLoading ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {[...Array(3)].map((_, i) => (
              <Card key={i}>
                <CardContent className="p-4">
                  <div className="flex items-start gap-4">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-5 w-1/3" />
                      <Skeleton className="h-4 w-1/2" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </motion.div>
        ) : hasSearched ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="space-y-4"
          >
            {/* Result count */}
            <PaginationInfo
              currentPage={currentPage}
              itemsPerPage={ITEMS_PER_PAGE}
              totalItems={total}
            />

            {/* Company Results */}
            {companies.length > 0 && (
              <div className="space-y-3">
                {companies.map((company) => (
                  <motion.div
                    key={company.company_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    whileHover={{ scale: 1.01 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Card
                      className="cursor-pointer transition-shadow hover:shadow-md"
                      onClick={() => navigate(`/companies/${company.company_id}`)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-4">
                            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
                              <Building2 className="h-5 w-5 text-gray-600" />
                            </div>
                            <div>
                              <h3 className="font-medium text-gray-900">
                                {company.legal_name || company.raw_name || 'Unbekannt'}
                              </h3>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-500">
                                {company.legal_form && (
                                  <span className="flex items-center gap-1">
                                    <FileText className="h-3 w-3" />
                                    {company.legal_form}
                                  </span>
                                )}
                                {company.address_city && (
                                  <span className="flex items-center gap-1">
                                    <MapPin className="h-3 w-3" />
                                    {company.address_city}
                                  </span>
                                )}
                                {company.register_id && (
                                  <span className="text-gray-400">
                                    {company.register_id}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {company.status && (
                              <Badge className={getStatusColor(company.status)}>
                                {company.status}
                              </Badge>
                            )}
                            <ChevronRight className="h-5 w-5 text-gray-400" />
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            )}

            {/* Person Results */}
            {persons.length > 0 && (
              <div className="space-y-3">
                {persons.map((person) => (
                  <motion.div
                    key={person.person_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    whileHover={{ scale: 1.01 }}
                    transition={{ duration: 0.2 }}
                  >
                    <Card
                      className="cursor-pointer transition-shadow hover:shadow-md"
                      onClick={() => navigate(`/persons/${person.person_id}`)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-4">
                            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
                              <User className="h-5 w-5 text-blue-600" />
                            </div>
                            <div>
                              <h3 className="font-medium text-gray-900">
                                {person.first_name} {person.last_name}
                              </h3>
                              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-500">
                                {person.birth_year && (
                                  <span>*{person.birth_year}</span>
                                )}
                                {person.address_city && (
                                  <span className="flex items-center gap-1">
                                    <MapPin className="h-3 w-3" />
                                    {person.address_city}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                          <ChevronRight className="h-5 w-5 text-gray-400" />
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {(companies.length > 0 || persons.length > 0) && totalPages > 1 && (
              <div className="mt-8 flex flex-col items-center gap-4">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  onPageChange={handlePageChange}
                />
                <p className="text-sm text-gray-500">
                  Seite {currentPage} von {totalPages}
                </p>
              </div>
            )}

            {/* Empty State */}
            {companies.length === 0 && persons.length === 0 && (
              <Card>
                <CardContent className="py-12 text-center">
                  <Search className="mx-auto h-12 w-12 text-gray-300" />
                  <h3 className="mt-4 text-lg font-medium text-gray-900">
                    Keine Ergebnisse
                  </h3>
                  <p className="mt-2 text-gray-500">
                    Versuchen Sie es mit anderen Suchbegriffen.
                  </p>
                </CardContent>
              </Card>
            )}
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center text-gray-500"
          >
            <Search className="mx-auto h-16 w-16 text-gray-200" />
            <p className="mt-4">
              Geben Sie einen Suchbegriff ein und drücken Sie Enter
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

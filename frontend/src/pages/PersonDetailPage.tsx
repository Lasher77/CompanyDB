import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  User,
  MapPin,
  Calendar,
  Building2,
  Code,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { personsApi } from '@/lib/api'
import { formatDate, getStatusColor } from '@/lib/utils'
import type { PersonDetail } from '@/types'

export function PersonDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [person, setPerson] = useState<PersonDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return

    async function loadPerson() {
      setIsLoading(true)
      setError(null)
      try {
        const data = await personsApi.getById(id!)
        setPerson(data)
      } catch (err) {
        setError('Person nicht gefunden')
      } finally {
        setIsLoading(false)
      }
    }

    loadPerson()
  }, [id])

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Card>
          <CardContent className="p-6">
            <div className="space-y-4">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error || !person) {
    return (
      <div className="text-center py-12">
        <User className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-4 text-lg font-medium text-gray-900">{error}</h3>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/')}>
          Zurück zur Suche
        </Button>
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-6"
    >
      {/* Back button */}
      <Button
        variant="ghost"
        className="gap-2"
        onClick={() => navigate(-1)}
      >
        <ArrowLeft className="h-4 w-4" />
        Zurück
      </Button>

      {/* Header Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-100">
              <User className="h-7 w-7 text-blue-600" />
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-semibold text-gray-900">
                {person.first_name} {person.last_name}
              </h1>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600">
                {person.birth_year && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-4 w-4" />
                    *{person.birth_year}
                  </span>
                )}
                {person.address_city && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-4 w-4" />
                    {person.address_city}
                  </span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Übersicht</TabsTrigger>
          <TabsTrigger value="companies">
            Firmen ({person.related_companies.length})
          </TabsTrigger>
          <TabsTrigger value="json">Raw JSON</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview">
          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Persönliche Daten</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <span className="text-sm text-gray-500">Vorname</span>
                  <p className="font-medium">{person.first_name || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Nachname</span>
                  <p className="font-medium">{person.last_name || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Geburtsjahr</span>
                  <p className="font-medium">{person.birth_year || '-'}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Adresse</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <span className="text-sm text-gray-500">Stadt</span>
                  <p className="font-medium">{person.address_city || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Person ID</span>
                  <p className="font-mono text-sm">{person.person_id}</p>
                </div>
              </CardContent>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Verknüpfte Firmen</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold text-gray-900">
                  {person.related_companies.length}
                </p>
                <p className="text-sm text-gray-500">
                  Firmenverbindungen
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Companies Tab */}
        <TabsContent value="companies">
          {person.related_companies.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Building2 className="mx-auto h-12 w-12 text-gray-300" />
                <p className="mt-4 text-gray-500">Keine verknüpften Firmen</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {person.related_companies.map((company, idx) => (
                <Card key={`${company.company_id}-${idx}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
                          <Building2 className="h-5 w-5 text-gray-600" />
                        </div>
                        <div>
                          <Link
                            to={`/companies/${company.company_id}`}
                            className="font-medium text-gray-900 hover:text-blue-600"
                          >
                            {company.legal_name || company.raw_name}
                          </Link>
                          <p className="text-sm text-gray-500">
                            {company.role_description || company.role_type}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {company.status && (
                          <Badge className={getStatusColor(company.status)}>
                            {company.status}
                          </Badge>
                        )}
                        {company.role_date && (
                          <span className="flex items-center gap-1 text-sm text-gray-500">
                            <Calendar className="h-4 w-4" />
                            {formatDate(company.role_date)}
                          </span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* JSON Tab */}
        <TabsContent value="json">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Code className="h-4 w-4" />
                Raw JSON
              </CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-[600px] overflow-auto rounded-lg bg-gray-50 p-4 text-xs">
                {JSON.stringify(person.full_record, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}

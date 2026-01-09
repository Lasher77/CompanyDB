import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  Building2,
  MapPin,
  FileText,
  Calendar,
  User,
  Code,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { companiesApi } from '@/lib/api'
import { formatDate, formatDateTime, getStatusColor } from '@/lib/utils'
import type { CompanyDetail } from '@/types'

export function CompanyDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [company, setCompany] = useState<CompanyDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return

    async function loadCompany() {
      setIsLoading(true)
      setError(null)
      try {
        const data = await companiesApi.getById(id!)
        setCompany(data)
      } catch (err) {
        setError('Firma nicht gefunden')
      } finally {
        setIsLoading(false)
      }
    }

    loadCompany()
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
              <Skeleton className="h-4 w-2/3" />
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error || !company) {
    return (
      <div className="text-center py-12">
        <Building2 className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-4 text-lg font-medium text-gray-900">{error}</h3>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/')}>
          Zurück zur Suche
        </Button>
      </div>
    )
  }

  const fullRecord = company.full_record as Record<string, unknown>
  const events = (fullRecord.events as { items?: Array<{ date: string; type: string; description: string }> })?.items || []
  const segmentCodes = fullRecord.segmentCodes as Record<string, string[]> | undefined

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
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gray-100">
              <Building2 className="h-7 w-7 text-gray-600" />
            </div>
            <div className="flex-1">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-2xl font-semibold text-gray-900">
                    {company.legal_name || company.raw_name}
                  </h1>
                  {company.raw_name && company.legal_name && company.raw_name !== company.legal_name && (
                    <p className="text-gray-500">{company.raw_name}</p>
                  )}
                </div>
                {company.status && (
                  <Badge className={getStatusColor(company.status)}>
                    {company.status}
                  </Badge>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600">
                {company.legal_form && (
                  <span className="flex items-center gap-1">
                    <FileText className="h-4 w-4" />
                    {company.legal_form}
                  </span>
                )}
                {company.address_city && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-4 w-4" />
                    {company.address_city}
                    {company.address_country && `, ${company.address_country}`}
                  </span>
                )}
                {company.register_id && (
                  <span className="flex items-center gap-1">
                    <FileText className="h-4 w-4" />
                    {company.register_id}
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
          <TabsTrigger value="persons">
            Personen ({company.related_persons.length})
          </TabsTrigger>
          <TabsTrigger value="events">
            Events ({events.length})
          </TabsTrigger>
          <TabsTrigger value="json">Raw JSON</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview">
          <div className="grid gap-6 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Registerdaten</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <span className="text-sm text-gray-500">Register-ID</span>
                  <p className="font-medium">{company.register_id || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Unique Key</span>
                  <p className="font-medium">{company.register_unique_key || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Company ID</span>
                  <p className="font-mono text-sm">{company.company_id}</p>
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
                  <p className="font-medium">{company.address_city || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">PLZ</span>
                  <p className="font-medium">{company.address_postal_code || '-'}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Land</span>
                  <p className="font-medium">{company.address_country || '-'}</p>
                </div>
              </CardContent>
            </Card>

            {segmentCodes && Object.keys(segmentCodes).some(k => segmentCodes[k]?.length > 0) && (
              <Card className="md:col-span-2">
                <CardHeader>
                  <CardTitle className="text-base">Branchencodes</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-4">
                    {Object.entries(segmentCodes).map(([key, values]) => (
                      values && values.length > 0 && (
                        <div key={key}>
                          <span className="text-sm text-gray-500 uppercase">{key}</span>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {values.map((code: string) => (
                              <Badge key={code} variant="secondary">{code}</Badge>
                            ))}
                          </div>
                        </div>
                      )
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Metadaten</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-6">
                <div>
                  <span className="text-sm text-gray-500">Letztes Update</span>
                  <p className="font-medium">{formatDateTime(company.last_update_time)}</p>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Importiert am</span>
                  <p className="font-medium">{formatDateTime(company.created_at)}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Persons Tab */}
        <TabsContent value="persons">
          {company.related_persons.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <User className="mx-auto h-12 w-12 text-gray-300" />
                <p className="mt-4 text-gray-500">Keine verknüpften Personen</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {company.related_persons.map((person, idx) => (
                <Card key={`${person.person_id}-${idx}`}>
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
                          <User className="h-5 w-5 text-blue-600" />
                        </div>
                        <div>
                          <Link
                            to={`/persons/${person.person_id}`}
                            className="font-medium text-gray-900 hover:text-blue-600"
                          >
                            {person.first_name} {person.last_name}
                          </Link>
                          <p className="text-sm text-gray-500">
                            {person.role_description || person.role_type}
                          </p>
                        </div>
                      </div>
                      {person.role_date && (
                        <span className="flex items-center gap-1 text-sm text-gray-500">
                          <Calendar className="h-4 w-4" />
                          {formatDate(person.role_date)}
                        </span>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Events Tab */}
        <TabsContent value="events">
          {events.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Calendar className="mx-auto h-12 w-12 text-gray-300" />
                <p className="mt-4 text-gray-500">Keine Events vorhanden</p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-4">
                <div className="space-y-4">
                  {events.map((event, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-4 border-b pb-4 last:border-0 last:pb-0"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-100">
                        <Calendar className="h-4 w-4 text-gray-600" />
                      </div>
                      <div>
                        <p className="font-medium text-gray-900">
                          {event.description}
                        </p>
                        <div className="mt-1 flex items-center gap-2 text-sm text-gray-500">
                          <span>{formatDate(event.date)}</span>
                          <Badge variant="secondary">{event.type}</Badge>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
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
                {JSON.stringify(company.full_record, null, 2)}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </motion.div>
  )
}

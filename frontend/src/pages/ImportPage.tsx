import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Upload,
  FileText,
  HardDrive,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
  Copy,
  RotateCcw,
  Building2,
  User,
  FolderOpen,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { importApi } from '@/lib/api'
import { formatDateTime, getStatusColor, cn } from '@/lib/utils'
import type { ImportFile, ImportJob } from '@/types'

export function ImportPage() {
  // Files state
  const [files, setFiles] = useState<ImportFile[]>([])
  const [filesLoading, setFilesLoading] = useState(true)
  const [filesError, setFilesError] = useState<string | null>(null)
  const [fileSearch, setFileSearch] = useState('')

  // Jobs state
  const [jobs, setJobs] = useState<ImportJob[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)

  // Dialog state
  const [selectedFile, setSelectedFile] = useState<ImportFile | null>(null)
  const [isConfirmOpen, setIsConfirmOpen] = useState(false)
  const [isStarting, setIsStarting] = useState(false)

  // Load files
  const loadFiles = useCallback(async () => {
    setFilesLoading(true)
    setFilesError(null)
    try {
      const data = await importApi.listFiles()
      setFiles(data)
    } catch (err) {
      setFilesError('Fehler beim Laden der Dateien')
    } finally {
      setFilesLoading(false)
    }
  }, [])

  // Load jobs
  const loadJobs = useCallback(async () => {
    try {
      const data = await importApi.listJobs()
      setJobs(data)
    } catch (err) {
      console.error('Error loading jobs:', err)
    } finally {
      setJobsLoading(false)
    }
  }, [])

  // Initial load
  useEffect(() => {
    loadFiles()
    loadJobs()
  }, [loadFiles, loadJobs])

  // Poll for running jobs
  useEffect(() => {
    const hasRunningJobs = jobs.some((j) => j.status === 'running' || j.status === 'pending')
    if (!hasRunningJobs) return

    const interval = setInterval(() => {
      loadJobs()
    }, 3000)

    return () => clearInterval(interval)
  }, [jobs, loadJobs])

  // Start import
  const handleStartImport = async () => {
    if (!selectedFile) return

    setIsStarting(true)
    try {
      await importApi.startJob(selectedFile.filename)
      setIsConfirmOpen(false)
      setSelectedFile(null)
      loadJobs()
    } catch (err) {
      console.error('Error starting import:', err)
    } finally {
      setIsStarting(false)
    }
  }

  // Filter files
  const filteredFiles = files.filter((f) =>
    f.filename.toLowerCase().includes(fileSearch.toLowerCase())
  )

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-semibold text-gray-900">Datenimport</h1>
        <p className="mt-2 text-gray-600">
          Importieren Sie NorthData JSONL-Dumps in die Datenbank
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        {/* Available Files */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-medium text-gray-900">Verfügbare Dateien</h2>
            <Button variant="ghost" size="sm" onClick={loadFiles}>
              <RotateCcw className="h-4 w-4" />
            </Button>
          </div>

          {/* Search */}
          <Input
            placeholder="Dateien filtern..."
            value={fileSearch}
            onChange={(e) => setFileSearch(e.target.value)}
          />

          {/* Files list */}
          <AnimatePresence mode="wait">
            {filesLoading ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-3"
              >
                {[...Array(3)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-4">
                      <Skeleton className="h-5 w-2/3" />
                      <Skeleton className="mt-2 h-4 w-1/3" />
                    </CardContent>
                  </Card>
                ))}
              </motion.div>
            ) : filesError ? (
              <Card className="border-red-200 bg-red-50">
                <CardContent className="p-6 text-center">
                  <XCircle className="mx-auto h-8 w-8 text-red-400" />
                  <p className="mt-2 text-red-700">{filesError}</p>
                  <Button
                    variant="outline"
                    className="mt-4"
                    onClick={loadFiles}
                  >
                    Erneut versuchen
                  </Button>
                </CardContent>
              </Card>
            ) : filteredFiles.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                <Card>
                  <CardContent className="py-12 text-center">
                    <FolderOpen className="mx-auto h-12 w-12 text-gray-300" />
                    <h3 className="mt-4 text-lg font-medium text-gray-900">
                      Keine Dateien gefunden
                    </h3>
                    <p className="mt-2 text-sm text-gray-500">
                      Legen Sie JSONL-Dateien im <code className="rounded bg-gray-100 px-1">data/</code> Ordner ab
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-3"
              >
                {filteredFiles.map((file) => (
                  <motion.div
                    key={file.filename}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    whileHover={{ scale: 1.01 }}
                  >
                    <Card className="transition-shadow hover:shadow-md">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-100">
                              <FileText className="h-5 w-5 text-blue-600" />
                            </div>
                            <div>
                              <p className="font-medium text-gray-900">
                                {file.filename}
                              </p>
                              <p className="flex items-center gap-1 text-sm text-gray-500">
                                <HardDrive className="h-3 w-3" />
                                {file.size_human}
                              </p>
                            </div>
                          </div>
                          <Button
                            onClick={() => {
                              setSelectedFile(file)
                              setIsConfirmOpen(true)
                            }}
                          >
                            <Play className="mr-2 h-4 w-4" />
                            Importieren
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Recent Jobs */}
        <div className="space-y-4">
          <h2 className="text-lg font-medium text-gray-900">Import-Jobs</h2>

          <AnimatePresence mode="wait">
            {jobsLoading ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-3"
              >
                {[...Array(2)].map((_, i) => (
                  <Card key={i}>
                    <CardContent className="p-4">
                      <Skeleton className="h-5 w-1/2" />
                      <Skeleton className="mt-2 h-4 w-full" />
                    </CardContent>
                  </Card>
                ))}
              </motion.div>
            ) : jobs.length === 0 ? (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
              >
                <Card>
                  <CardContent className="py-12 text-center">
                    <Upload className="mx-auto h-12 w-12 text-gray-300" />
                    <h3 className="mt-4 text-lg font-medium text-gray-900">
                      Keine Import-Jobs
                    </h3>
                    <p className="mt-2 text-sm text-gray-500">
                      Starten Sie einen Import, um Daten zu laden
                    </p>
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-3"
              >
                {jobs.map((job) => (
                  <JobCard key={job.id} job={job} />
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Confirmation Dialog */}
      <Dialog open={isConfirmOpen} onOpenChange={setIsConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Import starten</DialogTitle>
            <DialogDescription>
              Möchten Sie den Import wirklich starten?
            </DialogDescription>
          </DialogHeader>

          {selectedFile && (
            <div className="space-y-4">
              <Card className="bg-gray-50">
                <CardContent className="p-4">
                  <div className="flex items-center gap-3">
                    <FileText className="h-8 w-8 text-blue-600" />
                    <div>
                      <p className="font-medium">{selectedFile.filename}</p>
                      <p className="text-sm text-gray-500">{selectedFile.size_human}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div className="flex gap-3">
                  <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-600" />
                  <div className="text-sm text-amber-800">
                    <p className="font-medium">Hinweise:</p>
                    <ul className="mt-1 list-inside list-disc space-y-1">
                      <li>Der Import kann je nach Dateigröße lange dauern</li>
                      <li>Der Import läuft im Hintergrund weiter</li>
                      <li>Sie können diese Seite schließen</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsConfirmOpen(false)}
              disabled={isStarting}
            >
              Abbrechen
            </Button>
            <Button onClick={handleStartImport} disabled={isStarting}>
              {isStarting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starte...
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Import starten
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Job Card Component
function JobCard({ job }: { job: ImportJob }) {
  const [showDetails, setShowDetails] = useState(false)
  const [copied, setCopied] = useState(false)

  const progress = job.total_lines
    ? Math.round((job.processed_lines / job.total_lines) * 100)
    : null

  const copyError = () => {
    if (job.error_message) {
      navigator.clipboard.writeText(job.error_message)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <Card className={cn(
      'transition-all',
      job.status === 'running' && 'border-blue-200 bg-blue-50/50'
    )}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3">
            {job.status === 'completed' && (
              <CheckCircle className="mt-0.5 h-5 w-5 text-green-500" />
            )}
            {job.status === 'failed' && (
              <XCircle className="mt-0.5 h-5 w-5 text-red-500" />
            )}
            {job.status === 'running' && (
              <Loader2 className="mt-0.5 h-5 w-5 animate-spin text-blue-500" />
            )}
            {job.status === 'pending' && (
              <Clock className="mt-0.5 h-5 w-5 text-gray-400" />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium text-gray-900">
                {job.filename}
              </p>
              <p className="text-sm text-gray-500">
                Gestartet: {formatDateTime(job.created_at)}
              </p>
            </div>
          </div>
          <Badge className={getStatusColor(job.status)}>
            {job.status}
          </Badge>
        </div>

        {/* Progress */}
        {(job.status === 'running' || job.status === 'pending') && (
          <div className="mt-4">
            {progress !== null ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {job.processed_lines.toLocaleString()} / {job.total_lines?.toLocaleString()} Zeilen
                  </span>
                  <span className="font-medium">{progress}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-gray-200">
                  <motion.div
                    className="h-full bg-blue-500"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Verarbeite {job.processed_lines.toLocaleString()} Zeilen...</span>
              </div>
            )}
          </div>
        )}

        {/* Completed stats */}
        {job.status === 'completed' && (
          <div className="mt-4 flex gap-6">
            <div className="flex items-center gap-2 text-sm">
              <Building2 className="h-4 w-4 text-gray-400" />
              <span className="font-medium">{job.companies_imported.toLocaleString()}</span>
              <span className="text-gray-500">Firmen</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <User className="h-4 w-4 text-gray-400" />
              <span className="font-medium">{job.persons_imported.toLocaleString()}</span>
              <span className="text-gray-500">Personen</span>
            </div>
          </div>
        )}

        {/* Error */}
        {job.status === 'failed' && job.error_message && (
          <div className="mt-4">
            <button
              onClick={() => setShowDetails(!showDetails)}
              className="text-sm font-medium text-red-600 hover:text-red-700"
            >
              {showDetails ? 'Details ausblenden' : 'Details anzeigen'}
            </button>
            <AnimatePresence>
              {showDetails && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="mt-2 rounded-lg bg-red-50 p-3">
                    <pre className="max-h-32 overflow-auto text-xs text-red-700">
                      {job.error_message}
                    </pre>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-2"
                      onClick={copyError}
                    >
                      <Copy className="mr-2 h-3 w-3" />
                      {copied ? 'Kopiert!' : 'Fehler kopieren'}
                    </Button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

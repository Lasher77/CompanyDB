import type {
  ImportFile,
  ImportJob,
  CompanyListResponse,
  CompanyDetail,
  PersonListResponse,
  PersonDetail,
  HealthResponse,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    message: string
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function fetchApi<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new ApiError(
        response.status,
        response.statusText,
        errorData.detail || `Request failed: ${response.statusText}`
      )
    }

    return response.json()
  } catch (error) {
    if (error instanceof ApiError) {
      throw error
    }
    throw new ApiError(0, 'Network Error', 'Unable to connect to server')
  }
}

// Health
export const healthApi = {
  check: () => fetchApi<HealthResponse>('/health'),
}

// Import API
export const importApi = {
  listFiles: () => fetchApi<ImportFile[]>('/imports/files'),

  listJobs: () => fetchApi<ImportJob[]>('/imports'),

  getJob: (id: string) => fetchApi<ImportJob>(`/imports/${id}`),

  startJob: (filename: string) =>
    fetchApi<ImportJob>('/imports', {
      method: 'POST',
      body: JSON.stringify({ filename }),
    }),
}

// Companies API
export const companiesApi = {
  search: (params: {
    q?: string
    status?: string
    legal_form?: string
    city?: string
    limit?: number
    offset?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params.q) searchParams.set('q', params.q)
    if (params.status) searchParams.set('status', params.status)
    if (params.legal_form) searchParams.set('legal_form', params.legal_form)
    if (params.city) searchParams.set('city', params.city)
    if (params.limit) searchParams.set('limit', params.limit.toString())
    if (params.offset) searchParams.set('offset', params.offset.toString())

    const query = searchParams.toString()
    return fetchApi<CompanyListResponse>(`/companies${query ? `?${query}` : ''}`)
  },

  getById: (companyId: string) =>
    fetchApi<CompanyDetail>(`/companies/${companyId}`),
}

// Persons API
export const personsApi = {
  search: (params: {
    q?: string
    city?: string
    limit?: number
    offset?: number
  }) => {
    const searchParams = new URLSearchParams()
    if (params.q) searchParams.set('q', params.q)
    if (params.city) searchParams.set('city', params.city)
    if (params.limit) searchParams.set('limit', params.limit.toString())
    if (params.offset) searchParams.set('offset', params.offset.toString())

    const query = searchParams.toString()
    return fetchApi<PersonListResponse>(`/persons${query ? `?${query}` : ''}`)
  },

  getById: (personId: string) =>
    fetchApi<PersonDetail>(`/persons/${personId}`),
}

// Import types
export interface ImportFile {
  filename: string
  size_bytes: number
  size_human: string
}

export interface ImportJob {
  id: string
  filename: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  total_lines: number | null
  processed_lines: number
  companies_imported: number
  persons_imported: number
  error_message: string | null
  created_at: string
  updated_at: string
}

// Company types
export interface CompanyListItem {
  id: number
  company_id: string
  raw_name: string | null
  legal_name: string | null
  legal_form: string | null
  status: string | null
  terminated: boolean | null
  address_city: string | null
  address_country: string | null
  register_id: string | null
}

export interface CompanyListResponse {
  items: CompanyListItem[]
  total: number
  limit: number
  offset: number
}

export interface CompanyPersonRole {
  person_id: string
  first_name: string | null
  last_name: string | null
  role_type: string | null
  role_description: string | null
  role_date: string | null
}

export interface CompanyDetail {
  id: number
  company_id: string
  raw_name: string | null
  legal_name: string | null
  legal_form: string | null
  status: string | null
  terminated: boolean | null
  register_unique_key: string | null
  register_id: string | null
  address_city: string | null
  address_postal_code: string | null
  address_country: string | null
  last_update_time: string | null
  full_record: Record<string, unknown>
  related_persons: CompanyPersonRole[]
  created_at: string
}

// Person types
export interface PersonListItem {
  id: number
  person_id: string
  first_name: string | null
  last_name: string | null
  birth_year: number | null
  address_city: string | null
}

export interface PersonListResponse {
  items: PersonListItem[]
  total: number
  limit: number
  offset: number
}

export interface PersonCompanyRole {
  company_id: string
  legal_name: string | null
  raw_name: string | null
  status: string | null
  role_type: string | null
  role_description: string | null
  role_date: string | null
}

export interface PersonDetail {
  id: number
  person_id: string
  first_name: string | null
  last_name: string | null
  birth_year: number | null
  address_city: string | null
  full_record: Record<string, unknown>
  related_companies: PersonCompanyRole[]
  created_at: string
}

// Health check
export interface HealthResponse {
  status: string
  postgres: string
  opensearch: string
}

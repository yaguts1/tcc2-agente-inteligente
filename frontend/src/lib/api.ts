/**
 * API Service for Monitor de Alertas de Reposicionamento
 * All endpoints use relative paths with credentials: "same-origin"
 */

import { getStoredToken, storeToken, storeUser, clearAuth } from './storage';

export interface ApiError {
  message: string;
  status: number;
  details?: any;
}

export class ApiException extends Error {
  status: number;
  details?: any;

  constructor(message: string, status: number, details?: any) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `Erro ${response.status}`;
    let errorDetails;

    try {
      const errorData = await response.json();
      // fastapi often returns { detail: { code: 'x', message: '...' } }
      if (errorData) {
        if (typeof errorData.message === 'string') {
          errorMessage = errorData.message;
        } else if (typeof errorData.error === 'string') {
          errorMessage = errorData.error;
        } else if (errorData.detail) {
          const det = errorData.detail;
          if (typeof det === 'string') {
            errorMessage = det;
          } else if (det && typeof det.message === 'string') {
            errorMessage = det.message;
          } else if (det && typeof det.code === 'string') {
            errorMessage = det.code;
          }
        }
      }
      errorDetails = errorData;
    } catch {
      errorMessage = response.statusText || errorMessage;
    }

    throw new ApiException(errorMessage, response.status, errorDetails);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

async function request<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  // DEBUG: log requests to help diagnose why calls to /api/* might not reach backend
  try {
    // avoid logging bodies for security, but show method and url
    // eslint-disable-next-line no-console
    console.debug('[api] request', url, options && options.method ? options.method : 'GET');
  } catch (_) {}

  // Add stored token to Authorization header if available
  const token = getStoredToken();
  const headers = new Headers({
    'Content-Type': 'application/json',
  });

  // Copy existing headers from options
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers.set(key, value);
      });
    } else if (Array.isArray(options.headers)) {
      options.headers.forEach(([key, value]) => {
        headers.set(key, value);
      });
    } else {
      Object.entries(options.headers).forEach(([key, value]) => {
        headers.set(key, String(value));
      });
    }
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let finalUrl = url;
  // Adjust URL for base path if needed
  if (url.startsWith('/api')) {
    const baseUrl = import.meta.env.BASE_URL;
    if (baseUrl && baseUrl !== '/') {
      finalUrl = `${baseUrl}${url.substring(1)}`;
    }
  }

  const response = await fetch(finalUrl, {
    // rely on same-origin behavior and Vite proxy in dev; use same-origin
    // to ensure cookies are handled by the dev server host.
    credentials: 'same-origin',
    headers,
    ...options,
  });

  return handleResponse<T>(response);
}

// Auth API
export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
}

export interface AuthResponse {
  username: string;
  display_name?: string | null;
  role?: string;
}

export const authApi = {
  login: async (data: LoginRequest) => {
    const response = await request<AuthResponse & { token?: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    // Store token and user info if provided
    if (response.token) {
      storeToken(response.token);
    }
    storeUser({
      username: response.username,
      display_name: response.display_name,
      role: response.role,
    });
    return response;
  },

  register: async (data: RegisterRequest) => {
    const response = await request<AuthResponse & { token?: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    // Store token and user info if provided
    if (response.token) {
      storeToken(response.token);
    }
    storeUser({
      username: response.username,
      display_name: response.display_name,
      role: response.role,
    });
    return response;
  },

  me: () => request<AuthResponse>('/api/auth/me'),

  logout: async () => {
    try {
      await request<void>('/api/auth/logout', {
        method: 'POST',
      });
    } finally {
      // Always clear local storage even if logout request fails
      clearAuth();
    }
  },
};

// Alert API
export interface Alert {
  id: string;
  patientName: string;
  room: string;
  bed: string;
  lastRepositioning: string;
  nextRepositioning: string;
  riskLevel: 'high' | 'medium' | 'low';
  status: 'pending' | 'acknowledged' | 'completed';
}

export interface AlertsResponse {
  alerts: Alert[];
}

export const alertsApi = {
  getAlerts: (horas?: number) => {
    const url = horas
      ? `/api/frontend/alerts?horas=${horas}`
      : '/api/frontend/alerts';
    return request<Alert[]>(url);
  },

  acknowledge: (id: string) =>
    request<void>(`/api/frontend/alerts/${id}/acknowledge`, {
      method: 'POST',
    }),

  complete: (id: string) =>
    request<void>(`/api/frontend/alerts/${id}/complete`, {
      method: 'POST',
    }),

  batchAcknowledge: (alertIds: string[]) =>
    request<{ ok: boolean; processed: number; failed: number; errors: Array<{ alert_id: string; error: string }> }>(
      '/api/frontend/alerts/batch/acknowledge',
      {
        method: 'POST',
        body: JSON.stringify({ alert_ids: alertIds }),
      }
    ),

  batchComplete: (alertIds: string[]) =>
    request<{ ok: boolean; processed: number; failed: number; errors: Array<{ alert_id: string; error: string }> }>(
      '/api/frontend/alerts/batch/complete',
      {
        method: 'POST',
        body: JSON.stringify({ alert_ids: alertIds }),
      }
    ),
};

// Timeline API
export interface TimelineEvent {
  id: number;
  paciente_id: string;
  paciente_name: string | null;
  ts: string;
  ts_ms: number;
  tipo: string;
  descricao: string | null;
}

export interface TimelineFilters {
  paciente_id?: string;
  tipo?: string;
  start_ms?: number;
  end_ms?: number;
  limit?: number;
}

export const timelineApi = {
  getEvents: (filters?: TimelineFilters) => {
    const params = new URLSearchParams();
    if (filters?.paciente_id) params.append('paciente_id', filters.paciente_id);
    if (filters?.tipo) params.append('tipo', filters.tipo);
    if (filters?.start_ms) params.append('start_ms', filters.start_ms.toString());
    if (filters?.end_ms) params.append('end_ms', filters.end_ms.toString());
    if (filters?.limit) params.append('limit', filters.limit.toString());
    
    const queryString = params.toString();
    return request<TimelineEvent[]>(`/api/timeline${queryString ? `?${queryString}` : ''}`);
  },
};

// Patients API
export interface Patient {
  id: string;
  name: string;
  room: string;
  bed: string;
  riskLevel: 'high' | 'medium' | 'low';
  repositioningInterval: number;
  createdAt: string;
  updatedAt: string;
}

export interface CreatePatientRequest {
  name: string;
  room: string;
  bed: string;
  riskLevel: 'high' | 'medium' | 'low';
  repositioningInterval: number;
}

// Simulation API
export interface SimulationRequest {
  duracao_horas: number;
  seed?: number;
  perfil: 'baixo' | 'medio' | 'alto';
}

export interface SimulationResult {
  success: boolean;
  eventos: number;
  alertas: number;
  duracao: number;
  error?: string;
  message?: string;
}

export const patientsApi = {
  getPatients: () => request<Patient[]>('/api/pacientes'),

  getPatient: (id: string) => request<Patient>(`/api/pacientes/${id}`),

  createPatient: (data: CreatePatientRequest) =>
    request<Patient>('/api/pacientes', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePatient: (id: string, data: Partial<CreatePatientRequest>) =>
    request<Patient>(`/api/pacientes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deletePatient: (id: string) =>
    request<void>(`/api/pacientes/${id}`, {
      method: 'DELETE',
    }),

  simulateData: (id: string, data: SimulationRequest) =>
    request<SimulationResult>(`/api/pacientes/${id}/simular`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Device Events API
export interface DeviceEvent {
  id: number;
  device_id: string;
  ts: string;
  ts_ms: number;
  payload: any;
  processed_at: string | null;
  created_at: string;
}

export interface BedStats {
  cama_id: string;
  count: number;
  first_event: string;
  last_event: string;
  current_patient: {
    id: string;
    name: string;
  } | null;
}

export interface DeviceEventsStats {
  total_orphans: number;
  beds: BedStats[];
}

export interface ReconcileResponse {
  processed: number;
  skipped: number;
  patient_name?: string;
  cama_id?: string;
  error?: string;
}

export const deviceEventsApi = {
  getEvents: () => request<DeviceEvent[]>('/api/device_events'),

  getStats: () => request<DeviceEventsStats>('/api/device_events/stats'),

  reconcile: () =>
    request<ReconcileResponse>('/api/device_events/reconcile', {
      method: 'POST',
    }),

  reconcileBed: (camaId: string) =>
    request<ReconcileResponse>(`/api/device_events/reconcile_bed/${camaId}`, {
      method: 'POST',
    }),
};

// Dashboard Stats API
export interface DashboardStats {
  activeAlerts: number;
  acknowledgedAlerts: number;
  completedToday: number;
  totalPatients: number;
  completionRate: number;
}

export const statsApi = {
  getStats: () => request<DashboardStats>('/api/stats'),
};

// Export API
export interface ExportParams {
  startDate?: string;
  endDate?: string;
  status?: 'pending' | 'acknowledged' | 'completed';
  patientId?: string;
}

export const formatDateForExport = (dateStr: string): string => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('pt-BR');
};

export const exportAlertsToCSV = async (params: ExportParams): Promise<void> => {
  const queryParams = new URLSearchParams();
  if (params.startDate) queryParams.append('start_date', params.startDate);
  if (params.endDate) queryParams.append('end_date', params.endDate);
  if (params.status) queryParams.append('status', params.status);
  if (params.patientId) queryParams.append('patient_id', params.patientId);

  const response = await request<Blob>(`/api/alerts/export/csv?${queryParams.toString()}`, {
    headers: {
      'Accept': 'text/csv',
    },
  });

  // Create download link
  const url = window.URL.createObjectURL(new Blob([response as any]));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `alertas_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
};

export const exportAlertsToPDF = async (params: ExportParams): Promise<void> => {
  const queryParams = new URLSearchParams();
  if (params.startDate) queryParams.append('start_date', params.startDate);
  if (params.endDate) queryParams.append('end_date', params.endDate);
  if (params.status) queryParams.append('status', params.status);
  if (params.patientId) queryParams.append('patient_id', params.patientId);

  const response = await request<Blob>(`/api/alerts/export/pdf?${queryParams.toString()}`, {
    headers: {
      'Accept': 'application/pdf',
    },
  });

  // Create download link
  const url = window.URL.createObjectURL(new Blob([response as any], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `alertas_${new Date().toISOString().split('T')[0]}.pdf`);
  document.body.appendChild(link);
  link.click();
  link.remove();
};

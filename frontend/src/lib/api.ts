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

  const response = await fetch(url, {
    // rely on same-origin behavior and Vite proxy in dev; use same-origin
    // to ensure cookies are handled by the dev server host.
    credentials: 'same-origin',
    headers,
    ...options,
  });

  // Handle 401 Unauthorized - clear auth and redirect to login
  if (response.status === 401) {
    clearAuth();
    // Redirect to login page on next render
    window.location.href = '/login';
  }

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
  ts: string;
  ts_ms: number;
  tipo: string;
  descricao: string | null;
}

export const timelineApi = {
  getEvents: () => request<TimelineEvent[]>('/api/timeline'),
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
  event_type: string;
  event_data: any;
  processed_at: string | null;
  created_at: string;
}

export const deviceEventsApi = {
  getEvents: () => request<DeviceEvent[]>('/api/device_events'),

  reconcile: () =>
    request<void>('/api/device_events/reconcile', {
      method: 'POST',
    }),

  reconcileAdmin: () =>
    request<void>('/admin/device_events/reconcile', {
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

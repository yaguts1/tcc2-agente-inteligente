/**
 * Hook para gerenciar filtros de alertas no WebSocket.
 * 
 * Permite filtrar alertas por:
 * - Severidade (low, medium, high, critical)
 * - ID do paciente
 * - Tipo de alerta
 */

import { useState, useCallback } from 'react';

export interface AlertFilters {
  severities?: string[];
  patientId?: string;
  alertTypes?: string[];
  severity?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status?: 'open' | 'acknowledged' | 'completed';
  searchText?: string;
  dateFrom?: Date;
  dateTo?: Date;
}

export interface FilterStats {
  totalReceived: number;
  totalFiltered: number;
  totalSent: number;
  filterPercentage: number;
}

/**
 * Hook para gerenciar filtros de alertas.
 * 
 * @param onFiltersChange - Callback quando filtros mudam
 * @returns Estado de filtros e funções para gerenciar
 */
export function useAlertFilters(onFiltersChange?: (filters: AlertFilters) => void) {
  const [filters, setFilters] = useState<AlertFilters>({});
  const [stats, setStats] = useState<FilterStats>({
    totalReceived: 0,
    totalFiltered: 0,
    totalSent: 0,
    filterPercentage: 0,
  });

  /**
   * Atualiza severidades dos filtros.
   */
  const setSeverities = useCallback((severities: string[] | undefined) => {
    const newFilters = { ...filters, severities };
    setFilters(newFilters);
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  /**
   * Atualiza paciente dos filtros.
   */
  const setPatientId = useCallback((patientId: string | undefined) => {
    const newFilters = { ...filters, patientId };
    setFilters(newFilters);
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  /**
   * Atualiza tipos de alerta dos filtros.
   */
  const setAlertTypes = useCallback((alertTypes: string[] | undefined) => {
    const newFilters = { ...filters, alertTypes };
    setFilters(newFilters);
    onFiltersChange?.(newFilters);
  }, [filters, onFiltersChange]);

  /**
   * Limpa todos os filtros.
   */
  const clearFilters = useCallback(() => {
    const newFilters: AlertFilters = {};
    setFilters(newFilters);
    onFiltersChange?.(newFilters);
  }, [onFiltersChange]);

  /**
   * Atualiza estatísticas de filtros.
   */
  const updateStats = useCallback((
    totalReceived: number,
    totalFiltered: number,
    totalSent: number,
  ) => {
    const filterPercentage =
      totalReceived > 0 ? (totalFiltered / totalReceived) * 100 : 0;

    setStats({
      totalReceived,
      totalFiltered,
      totalSent,
      filterPercentage,
    });
  }, []);

  /**
   * Converte filtros para query string.
   */
  const toQueryString = useCallback(() => {
    const params = new URLSearchParams();

    if (filters.severities && filters.severities.length > 0) {
      params.append('severity', filters.severities.join(','));
    }

    if (filters.patientId) {
      params.append('patient_id', filters.patientId);
    }

    if (filters.alertTypes && filters.alertTypes.length > 0) {
      params.append('alert_types', filters.alertTypes.join(','));
    }

    return params.toString();
  }, [filters]);

  /**
   * Converte filtros para objeto WebSocket URL.
   */
  const toWebSocketURL = useCallback(() => {
    const queryString = toQueryString();
    const baseURL =
      process.env.NODE_ENV === 'development'
        ? 'ws://localhost:8000/api/ws/alerts'
        : `wss://${window.location.host}/api/ws/alerts`;

    return queryString ? `${baseURL}?${queryString}` : baseURL;
  }, [toQueryString]);

  return {
    filters,
    stats,
    setSeverities,
    setPatientId,
    setAlertTypes,
    clearFilters,
    updateStats,
    toQueryString,
    toWebSocketURL,
  };
}

/**
 * Hook para gerenciar pré-sets de filtros comuns.
 */
export function useAlertFilterPresets() {
  const [filters, setFilters] = useState<AlertFilters>({});

  const presets = {
    critical: { severities: ['critical'] },
    highAndCritical: { severities: ['high', 'critical'] },
    allSeverities: {
      severities: ['low', 'medium', 'high', 'critical'],
    },
    custom: filters,
  };

  return {
    filters,
    presets,
    applyPreset: (preset: AlertFilters) => setFilters(preset),
    setCustom: (custom: AlertFilters) => setFilters(custom),
  };
}

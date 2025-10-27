import React, { useState } from 'react';
import { exportAlertsToCSV, exportAlertsToPDF, formatDateForExport } from '../lib/exportApi';
import { ApiException } from '../lib/api';
import './ExportPanel.css';

interface ExportPanelProps {
  onSuccess?: (message: string) => void;
  onError?: (message: string) => void;
}

export function ExportPanel({ onSuccess, onError }: ExportPanelProps) {
  const [filters, setFilters] = useState({
    startDate: '',
    endDate: '',
    status: 'all',
    patientId: '',
    format: 'csv' as 'csv' | 'pdf',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFilters(prev => ({
      ...prev,
      [name]: value,
    }));
    setError(null);
  };

  const validateFilters = (): boolean => {
    if (filters.startDate && filters.endDate) {
      const start = new Date(filters.startDate);
      const end = new Date(filters.endDate);
      if (start > end) {
        setError('A data inicial deve ser anterior à data final');
        return false;
      }
    }
    return true;
  };

  const handleReset = () => {
    setFilters({
      startDate: '',
      endDate: '',
      status: 'all',
      patientId: '',
      format: 'csv',
    });
    setError(null);
  };

  const handleExport = async () => {
    if (!validateFilters()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const exportParams = {
        startDate: filters.startDate || undefined,
        endDate: filters.endDate || undefined,
        status: filters.status === 'all' ? undefined : (filters.status as any),
        patientId: filters.patientId || undefined,
      };

      if (filters.format === 'csv') {
        await exportAlertsToCSV(exportParams);
        onSuccess?.('CSV exportado com sucesso!');
      } else {
        await exportAlertsToPDF(exportParams);
        onSuccess?.('PDF exportado com sucesso!');
      }
    } catch (err: unknown) {
      const message = err instanceof ApiException ? err.message : 'Erro ao exportar dados';
      setError(message);
      onError?.(message);
      console.error('Export error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="export-panel">
      <div className="export-header">
        <h3>📊 Exportar Dados</h3>
      </div>

      <div className="export-content">
        {/* Date Range */}
        <div className="filter-group">
          <label htmlFor="startDate">Data Inicial:</label>
          <input
            type="date"
            id="startDate"
            name="startDate"
            value={filters.startDate}
            onChange={handleFilterChange}
            disabled={loading}
          />
        </div>

        <div className="filter-group">
          <label htmlFor="endDate">Data Final:</label>
          <input
            type="date"
            id="endDate"
            name="endDate"
            value={filters.endDate}
            onChange={handleFilterChange}
            disabled={loading}
          />
        </div>

        {/* Status Filter */}
        <div className="filter-group">
          <label htmlFor="status">Status:</label>
          <select
            id="status"
            name="status"
            value={filters.status}
            onChange={handleFilterChange}
            disabled={loading}
          >
            <option value="all">Todos</option>
            <option value="pending">Pendente</option>
            <option value="acknowledged">Reconhecido</option>
            <option value="completed">Concluído</option>
          </select>
        </div>

        {/* Patient ID */}
        <div className="filter-group">
          <label htmlFor="patientId">ID do Paciente:</label>
          <input
            type="text"
            id="patientId"
            name="patientId"
            placeholder="Ex: PAC-0001"
            value={filters.patientId}
            onChange={handleFilterChange}
            disabled={loading}
          />
        </div>

        {/* Format Selector */}
        <div className="filter-group format-selector">
          <label>Formato:</label>
          <div className="radio-group">
            <label className="radio-label">
              <input
                type="radio"
                name="format"
                value="csv"
                checked={filters.format === 'csv'}
                onChange={handleFilterChange}
                disabled={loading}
              />
              CSV
            </label>
            <label className="radio-label">
              <input
                type="radio"
                name="format"
                value="pdf"
                checked={filters.format === 'pdf'}
                onChange={handleFilterChange}
                disabled={loading}
              />
              PDF
            </label>
          </div>
        </div>

        {/* Error Message */}
        {error && (
          <div className="error-message">
            <span>⚠️ {error}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="button-group">
          <button
            className="btn btn-primary"
            onClick={handleExport}
            disabled={loading}
          >
            {loading ? '⏳ Exportando...' : `📥 Baixar ${filters.format.toUpperCase()}`}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleReset}
            disabled={loading}
          >
            🔄 Limpar
          </button>
        </div>

        {/* Info */}
        <div className="info-message">
          <p>
            💡 <strong>Dica:</strong> Deixe os campos em branco para incluir todos os dados. 
            Use as datas para filtrar por período específico.
          </p>
        </div>
      </div>
    </div>
  );
}

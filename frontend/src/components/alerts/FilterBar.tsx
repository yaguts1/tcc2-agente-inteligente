import React, { useState, useCallback } from 'react';
import { X, Filter, Calendar, Search } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../ui/popover';
import { Badge } from '../ui/badge';
import { AlertFilters } from '../../hooks/useAlertFilters';

interface FilterBarProps {
  filters: AlertFilters;
  onFilterChange: (key: keyof AlertFilters, value: any) => void;
  onClearFilters: () => void;
  activeFilterCount: number;
  patients?: Array<{ id: string; name: string }>;
}

const SEVERITY_OPTIONS = [
  { value: 'LOW', label: 'Baixa', color: 'bg-blue-100 text-blue-800' },
  { value: 'MEDIUM', label: 'Média', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'HIGH', label: 'Alta', color: 'bg-orange-100 text-orange-800' },
  { value: 'CRITICAL', label: 'Crítica', color: 'bg-red-100 text-red-800' },
];

const STATUS_OPTIONS = [
  { value: 'open', label: 'Aberto', color: 'bg-blue-100 text-blue-800' },
  { value: 'acknowledged', label: 'Reconhecido', color: 'bg-yellow-100 text-yellow-800' },
  { value: 'completed', label: 'Completo', color: 'bg-green-100 text-green-800' },
];

export function FilterBar({
  filters,
  onFilterChange,
  onClearFilters,
  activeFilterCount,
  patients = [],
}: FilterBarProps) {
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onFilterChange('searchText', e.target.value || undefined);
    },
    [onFilterChange]
  );

  const handleDateFromChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const date = e.target.value ? new Date(e.target.value) : undefined;
      onFilterChange('dateFrom', date);
    },
    [onFilterChange]
  );

  const handleDateToChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const date = e.target.value ? new Date(e.target.value) : undefined;
      onFilterChange('dateTo', date);
    },
    [onFilterChange]
  );

  const getSeverityBadge = (severity: string) => {
    const option = SEVERITY_OPTIONS.find((opt) => opt.value === severity);
    return option ? { label: option.label, color: option.color } : null;
  };

  const getStatusBadge = (status: string) => {
    const option = STATUS_OPTIONS.find((opt) => opt.value === status);
    return option ? { label: option.label, color: option.color } : null;
  };

  const getPatientName = (id: string) => {
    return patients.find((p) => p.id === id)?.name || id;
  };

  const dateFromValue = filters.dateFrom
    ? new Date(filters.dateFrom).toISOString().split('T')[0]
    : '';

  const dateToValue = filters.dateTo
    ? new Date(filters.dateTo).toISOString().split('T')[0]
    : '';

  return (
    <div className="space-y-3 mb-6 p-4 bg-gray-50 rounded-lg border border-gray-200">
      {/* Filter Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-gray-600" />
          <span className="text-sm font-medium text-gray-700">Filtros</span>
          {activeFilterCount > 0 && (
            <Badge variant="secondary" className="ml-2">
              {activeFilterCount} ativo{activeFilterCount !== 1 ? 's' : ''}
            </Badge>
          )}
        </div>
        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="text-gray-600 hover:text-gray-900"
          >
            <X className="w-4 h-4 mr-1" />
            Limpar tudo
          </Button>
        )}
      </div>

      {/* Active Filters Display */}
      {(filters.severity || filters.status || filters.patientId || filters.searchText) && (
        <div className="flex flex-wrap gap-2 mb-3">
          {filters.severity && (
            <Badge
              variant="outline"
              className={`${getSeverityBadge(filters.severity)?.color}`}
            >
              Severidade: {getSeverityBadge(filters.severity)?.label}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => onFilterChange('severity', undefined)}
              />
            </Badge>
          )}
          {filters.status && (
            <Badge
              variant="outline"
              className={`${getStatusBadge(filters.status)?.color}`}
            >
              Status: {getStatusBadge(filters.status)?.label}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => onFilterChange('status', undefined)}
              />
            </Badge>
          )}
          {filters.patientId && (
            <Badge variant="outline">
              Paciente: {getPatientName(filters.patientId)}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => onFilterChange('patientId', undefined)}
              />
            </Badge>
          )}
          {filters.searchText && (
            <Badge variant="outline">
              Busca: "{filters.searchText}"
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => onFilterChange('searchText', undefined)}
              />
            </Badge>
          )}
          {(filters.dateFrom || filters.dateTo) && (
            <Badge variant="outline">
              Data: {filters.dateFrom ? new Date(filters.dateFrom).toLocaleDateString('pt-BR') : 'início'} a{' '}
              {filters.dateTo ? new Date(filters.dateTo).toLocaleDateString('pt-BR') : 'hoje'}
              <X
                className="w-3 h-3 ml-1 cursor-pointer"
                onClick={() => {
                  onFilterChange('dateFrom', undefined);
                  onFilterChange('dateTo', undefined);
                }}
              />
            </Badge>
          )}
        </div>
      )}

      {/* Filter Controls */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
          <Input
            placeholder="Buscar título, descrição..."
            value={filters.searchText || ''}
            onChange={handleSearchChange}
            className="pl-8"
          />
        </div>

        {/* Severity */}
        <Select value={filters.severity || ''} onValueChange={(value: string) => 
          onFilterChange('severity', value || undefined)
        }>
          <SelectTrigger>
            <SelectValue placeholder="Severidade" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">Todas</SelectItem>
            {SEVERITY_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Status */}
        <Select value={filters.status || ''} onValueChange={(value: string) => 
          onFilterChange('status', value || undefined)
        }>
          <SelectTrigger>
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">Todos</SelectItem>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Patient */}
        {patients.length > 0 && (
          <Select value={filters.patientId || ''} onValueChange={(value: string) => 
            onFilterChange('patientId', value || undefined)
          }>
            <SelectTrigger>
              <SelectValue placeholder="Paciente" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Todos</SelectItem>
              {patients.map((patient) => (
                <SelectItem key={patient.id} value={patient.id}>
                  {patient.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {/* Date Range */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className="w-full justify-start text-left font-normal"
            >
              <Calendar className="mr-2 h-4 w-4" />
              Data
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80">
            <div className="space-y-2">
              <div>
                <label className="text-sm font-medium">De</label>
                <Input
                  type="date"
                  value={dateFromValue}
                  onChange={handleDateFromChange}
                />
              </div>
              <div>
                <label className="text-sm font-medium">Até</label>
                <Input
                  type="date"
                  value={dateToValue}
                  onChange={handleDateToChange}
                />
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}

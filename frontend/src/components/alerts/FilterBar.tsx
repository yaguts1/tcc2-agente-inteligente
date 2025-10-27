import React, { useState, useCallback } from 'react';
import { X, Filter, Calendar, Search, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
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
import { Card } from '../ui/card';
import { AlertFilters } from '../../hooks/useAlertFilters';

interface FilterBarProps {
  filters: AlertFilters;
  onFilterChange: (key: keyof AlertFilters, value: any) => void;
  onClearFilters: () => void;
  activeFilterCount: number;
  patients?: Array<{ id: string; name: string }>;
}

const SEVERITY_OPTIONS = [
  { value: 'LOW', label: 'Baixa' },
  { value: 'MEDIUM', label: 'Média' },
  { value: 'HIGH', label: 'Alta' },
  { value: 'CRITICAL', label: 'Crítica' },
];

const STATUS_OPTIONS = [
  { value: 'open', label: 'Aberto' },
  { value: 'acknowledged', label: 'Reconhecido' },
  { value: 'completed', label: 'Completo' },
];

export function FilterBar({
  filters,
  onFilterChange,
  onClearFilters,
  activeFilterCount,
  patients = [],
}: FilterBarProps) {
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

  const getSeverityLabel = (severity: string) => {
    return SEVERITY_OPTIONS.find((opt) => opt.value === severity)?.label || severity;
  };

  const getStatusLabel = (status: string) => {
    return STATUS_OPTIONS.find((opt) => opt.value === status)?.label || status;
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
    <Card className="p-4 space-y-4">
      {/* Filter Header with active count */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Filter className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h3 className="font-semibold text-sm">Filtros</h3>
            <p className="text-xs text-muted-foreground">
              {activeFilterCount === 0
                ? 'Nenhum filtro aplicado'
                : `${activeFilterCount} filtro${activeFilterCount !== 1 ? 's' : ''} ativo${activeFilterCount !== 1 ? 's' : ''}`}
            </p>
          </div>
        </div>
        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearFilters}
            className="text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            <X className="w-4 h-4 mr-1" />
            Limpar
          </Button>
        )}
      </div>

      {/* Active Filters Display as Removable Badges */}
      {activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-2 p-3 bg-muted/50 rounded-lg">
          {filters.severity && (
            <Badge
              variant="secondary"
              className="cursor-pointer hover:bg-secondary/80 transition-colors"
              onClick={() => onFilterChange('severity', undefined)}
            >
              <AlertCircle className="w-3 h-3 mr-1" />
              Severidade: {getSeverityLabel(filters.severity)}
              <X className="w-3 h-3 ml-2" />
            </Badge>
          )}
          {filters.status && (
            <Badge
              variant="secondary"
              className="cursor-pointer hover:bg-secondary/80 transition-colors"
              onClick={() => onFilterChange('status', undefined)}
            >
              Status: {getStatusLabel(filters.status)}
              <X className="w-3 h-3 ml-2" />
            </Badge>
          )}
          {filters.patientId && (
            <Badge
              variant="secondary"
              className="cursor-pointer hover:bg-secondary/80 transition-colors"
              onClick={() => onFilterChange('patientId', undefined)}
            >
              Paciente: {getPatientName(filters.patientId)}
              <X className="w-3 h-3 ml-2" />
            </Badge>
          )}
          {filters.searchText && (
            <Badge
              variant="secondary"
              className="cursor-pointer hover:bg-secondary/80 transition-colors"
              onClick={() => onFilterChange('searchText', undefined)}
            >
              Busca: "{filters.searchText}"
              <X className="w-3 h-3 ml-2" />
            </Badge>
          )}
          {(filters.dateFrom || filters.dateTo) && (
            <Badge
              variant="secondary"
              className="cursor-pointer hover:bg-secondary/80 transition-colors"
              onClick={() => {
                onFilterChange('dateFrom', undefined);
                onFilterChange('dateTo', undefined);
              }}
            >
              Data: {filters.dateFrom ? new Date(filters.dateFrom).toLocaleDateString('pt-BR') : 'início'} a{' '}
              {filters.dateTo ? new Date(filters.dateTo).toLocaleDateString('pt-BR') : 'hoje'}
              <X className="w-3 h-3 ml-2" />
            </Badge>
          )}
        </div>
      )}

      {/* Filter Controls - Organized by section */}
      <div className="space-y-4">
        {/* Search Row */}
        <div>
          <Label htmlFor="search-input" className="text-xs font-medium mb-2 block">
            Buscar
          </Label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="search-input"
              placeholder="Título, descrição, código do paciente..."
              value={filters.searchText || ''}
              onChange={handleSearchChange}
              className="pl-9"
            />
          </div>
        </div>

        {/* Filter Selects - Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Severity */}
          <div>
            <Label htmlFor="severity-select" className="text-xs font-medium mb-2 block">
              Severidade
            </Label>
            <Select
              value={filters.severity || 'all'}
              onValueChange={(value: string) =>
                onFilterChange('severity', value === 'all' ? undefined : value)
              }
            >
              <SelectTrigger id="severity-select">
                <SelectValue placeholder="Todas" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                {SEVERITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Status */}
          <div>
            <Label htmlFor="status-select" className="text-xs font-medium mb-2 block">
              Status
            </Label>
            <Select
              value={filters.status || 'all'}
              onValueChange={(value: string) =>
                onFilterChange('status', value === 'all' ? undefined : value)
              }
            >
              <SelectTrigger id="status-select">
                <SelectValue placeholder="Todos" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Patient - only show if we have patients */}
          {patients.length > 0 && (
            <div>
              <Label htmlFor="patient-select" className="text-xs font-medium mb-2 block">
                Paciente
              </Label>
              <Select
                value={filters.patientId || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('patientId', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="patient-select">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {patients.map((patient) => (
                    <SelectItem key={patient.id} value={patient.id}>
                      {patient.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* Date Range */}
        <div>
          <Label className="text-xs font-medium mb-2 block">Período</Label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className="w-full justify-start text-left font-normal"
                >
                  <Calendar className="mr-2 h-4 w-4" />
                  {filters.dateFrom
                    ? new Date(filters.dateFrom).toLocaleDateString('pt-BR')
                    : 'Data inicial'}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-3" align="start">
                <Label htmlFor="date-from" className="text-xs font-medium">
                  De
                </Label>
                <Input
                  id="date-from"
                  type="date"
                  value={dateFromValue}
                  onChange={handleDateFromChange}
                  className="mt-1"
                />
              </PopoverContent>
            </Popover>

            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className="w-full justify-start text-left font-normal"
                >
                  <Calendar className="mr-2 h-4 w-4" />
                  {filters.dateTo
                    ? new Date(filters.dateTo).toLocaleDateString('pt-BR')
                    : 'Data final'}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-3" align="start">
                <Label htmlFor="date-to" className="text-xs font-medium">
                  Até
                </Label>
                <Input
                  id="date-to"
                  type="date"
                  value={dateToValue}
                  onChange={handleDateToChange}
                  className="mt-1"
                />
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </div>
    </Card>
  );
}

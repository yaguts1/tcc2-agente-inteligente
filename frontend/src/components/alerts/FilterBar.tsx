import React, { useState, useCallback } from 'react';
import { X, Filter, Calendar, Search, ChevronDown } from 'lucide-react';
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
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '../ui/collapsible';
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
  const [isOpen, setIsOpen] = useState(false);

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
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="space-y-2 mb-4">
      {/* Compact Header - Always visible */}
      <CollapsibleTrigger asChild>
        <Button
          variant="outline"
          className="w-full justify-between h-10"
          size="sm"
        >
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4" />
            <span className="text-sm">
              Filtros {activeFilterCount > 0 && `(${activeFilterCount})`}
            </span>
          </div>
          <ChevronDown
            className="w-4 h-4 transition-transform"
            style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
          />
        </Button>
      </CollapsibleTrigger>

      {/* Active Filters as inline badges when collapsed */}
      {!isOpen && activeFilterCount > 0 && (
        <div className="flex flex-wrap gap-1">
          {filters.severity && (
            <Badge
              variant="secondary"
              className="cursor-pointer text-xs py-0.5"
              onClick={() => onFilterChange('severity', undefined)}
            >
              {getSeverityLabel(filters.severity)}
              <X className="w-3 h-3 ml-1" />
            </Badge>
          )}
          {filters.status && (
            <Badge
              variant="secondary"
              className="cursor-pointer text-xs py-0.5"
              onClick={() => onFilterChange('status', undefined)}
            >
              {getStatusLabel(filters.status)}
              <X className="w-3 h-3 ml-1" />
            </Badge>
          )}
          {filters.patientId && (
            <Badge
              variant="secondary"
              className="cursor-pointer text-xs py-0.5"
              onClick={() => onFilterChange('patientId', undefined)}
            >
              {getPatientName(filters.patientId).substring(0, 10)}
              <X className="w-3 h-3 ml-1" />
            </Badge>
          )}
          {filters.searchText && (
            <Badge
              variant="secondary"
              className="cursor-pointer text-xs py-0.5"
              onClick={() => onFilterChange('searchText', undefined)}
            >
              "{filters.searchText.substring(0, 8)}"
              <X className="w-3 h-3 ml-1" />
            </Badge>
          )}
          {(filters.dateFrom || filters.dateTo) && (
            <Badge
              variant="secondary"
              className="cursor-pointer text-xs py-0.5"
              onClick={() => {
                onFilterChange('dateFrom', undefined);
                onFilterChange('dateTo', undefined);
              }}
            >
              Data
              <X className="w-3 h-3 ml-1" />
            </Badge>
          )}
        </div>
      )}

      <CollapsibleContent className="pt-2 space-y-3 border-t">
        {/* Active Filters Display - Full version when expanded */}
        {activeFilterCount > 0 && (
          <div className="flex flex-wrap gap-2 p-2 bg-muted/50 rounded">
            {filters.severity && (
              <Badge
                variant="secondary"
                className="cursor-pointer"
                onClick={() => onFilterChange('severity', undefined)}
              >
                Severidade: {getSeverityLabel(filters.severity)}
                <X className="w-3 h-3 ml-2" />
              </Badge>
            )}
            {filters.status && (
              <Badge
                variant="secondary"
                className="cursor-pointer"
                onClick={() => onFilterChange('status', undefined)}
              >
                Status: {getStatusLabel(filters.status)}
                <X className="w-3 h-3 ml-2" />
              </Badge>
            )}
            {filters.patientId && (
              <Badge
                variant="secondary"
                className="cursor-pointer"
                onClick={() => onFilterChange('patientId', undefined)}
              >
                Paciente: {getPatientName(filters.patientId)}
                <X className="w-3 h-3 ml-2" />
              </Badge>
            )}
            {filters.searchText && (
              <Badge
                variant="secondary"
                className="cursor-pointer"
                onClick={() => onFilterChange('searchText', undefined)}
              >
                Busca: "{filters.searchText}"
                <X className="w-3 h-3 ml-2" />
              </Badge>
            )}
            {(filters.dateFrom || filters.dateTo) && (
              <Badge
                variant="secondary"
                className="cursor-pointer"
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
            {activeFilterCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onClearFilters}
                className="text-destructive hover:text-destructive hover:bg-destructive/10 h-7 text-xs"
              >
                <X className="w-3 h-3 mr-1" />
                Limpar
              </Button>
            )}
          </div>
        )}

        {/* Filter Controls - Grid when expanded */}
        <div className="space-y-3">
          {/* Search */}
          <div>
            <Label htmlFor="filter-search" className="text-xs font-medium mb-1 block">
              Buscar por título, descrição ou paciente
            </Label>
            <Input
              id="filter-search"
              placeholder="Digite para buscar..."
              value={filters.searchText || ''}
              onChange={handleSearchChange}
              className="h-9"
            />
          </div>

          {/* Filter Grid */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {/* Severity */}
            <div>
              <Label htmlFor="filter-severity" className="text-xs font-medium mb-1 block">
                Severidade
              </Label>
              <Select
                value={filters.severity || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('severity', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="filter-severity" className="h-9">
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
              <Label htmlFor="filter-status" className="text-xs font-medium mb-1 block">
                Status
              </Label>
              <Select
                value={filters.status || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('status', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="filter-status" className="h-9">
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
                <Label htmlFor="filter-patient" className="text-xs font-medium mb-1 block">
                  Paciente
                </Label>
                <Select
                  value={filters.patientId || 'all'}
                  onValueChange={(value: string) =>
                    onFilterChange('patientId', value === 'all' ? undefined : value)
                  }
                >
                  <SelectTrigger id="filter-patient" className="h-9">
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

            {/* Date Range Compact */}
            <Popover>
              <PopoverTrigger asChild>
                <div>
                  <Label className="text-xs font-medium mb-1 block">
                    Período
                  </Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-9 justify-start text-left font-normal w-full"
                  >
                    <Calendar className="mr-1.5 h-3 w-3" />
                    Data
                  </Button>
                </div>
              </PopoverTrigger>
              <PopoverContent className="w-64 p-3">
                <div className="space-y-2">
                  <div>
                    <Label className="text-xs">De</Label>
                    <Input
                      type="date"
                      value={dateFromValue}
                      onChange={handleDateFromChange}
                      className="h-8 text-xs mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Até</Label>
                    <Input
                      type="date"
                      value={dateToValue}
                      onChange={handleDateToChange}
                      className="h-8 text-xs mt-1"
                    />
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

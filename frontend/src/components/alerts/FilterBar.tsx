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
  { value: 'pending', label: 'Pendente' },
  { value: 'acknowledged', label: 'Reconhecido' },
  { value: 'completed', label: 'Completado' },
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
    <div className="bg-card border border-border rounded-lg p-4 space-y-4">
      <Collapsible open={isOpen} onOpenChange={setIsOpen} className="space-y-3">
        {/* Compact Header - Always visible */}
        <div className="flex items-center justify-between">
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              className="flex items-center gap-2 h-auto p-0 hover:bg-transparent"
              size="sm"
            >
              <Filter className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">
                Filtros {activeFilterCount > 0 && (
                  <span className="ml-1 text-xs bg-primary text-primary-foreground rounded-full px-2 py-0.5">
                    {activeFilterCount}
                  </span>
                )}
              </span>
              <ChevronDown
                className="w-4 h-4 text-muted-foreground transition-transform"
                style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
              />
            </Button>
          </CollapsibleTrigger>
          
          {activeFilterCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearFilters}
              className="text-xs text-muted-foreground hover:text-destructive h-7"
            >
              <X className="w-3 h-3 mr-1" />
              Limpar todos
            </Button>
          )}
        </div>

        {/* Active Filters as inline badges when collapsed */}
        {!isOpen && activeFilterCount > 0 && (
          <div className="flex flex-wrap gap-2 mt-2">
            {filters.severity && (
              <Badge
                variant="secondary"
                className="cursor-pointer hover:bg-secondary/80 transition-colors"
                onClick={() => onFilterChange('severity', undefined)}
              >
                Severidade: {getSeverityLabel(filters.severity)}
                <X className="w-3 h-3 ml-1.5" />
              </Badge>
            )}
            {filters.status && (
              <Badge
                variant="secondary"
                className="cursor-pointer hover:bg-secondary/80 transition-colors"
                onClick={() => onFilterChange('status', undefined)}
              >
                Status: {getStatusLabel(filters.status)}
                <X className="w-3 h-3 ml-1.5" />
              </Badge>
            )}
            {filters.patientId && (
              <Badge
                variant="secondary"
                className="cursor-pointer hover:bg-secondary/80 transition-colors"
                onClick={() => onFilterChange('patientId', undefined)}
              >
                Paciente: {getPatientName(filters.patientId)}
                <X className="w-3 h-3 ml-1.5" />
              </Badge>
            )}
            {filters.searchText && (
              <Badge
                variant="secondary"
                className="cursor-pointer hover:bg-secondary/80 transition-colors"
                onClick={() => onFilterChange('searchText', undefined)}
              >
                Busca: "{filters.searchText.substring(0, 20)}{filters.searchText.length > 20 ? '...' : ''}"
                <X className="w-3 h-3 ml-1.5" />
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
                <Calendar className="w-3 h-3 mr-1" />
                Período
                <X className="w-3 h-3 ml-1.5" />
              </Badge>
            )}
          </div>
        )}

        <CollapsibleContent className="space-y-4">
          {/* Search */}
          <div>
            <Label htmlFor="filter-search" className="text-sm font-medium mb-2 block">
              <Search className="w-4 h-4 inline mr-1.5 text-muted-foreground" />
              Buscar
            </Label>
            <Input
              id="filter-search"
              placeholder="Buscar por paciente, quarto, leito..."
              value={filters.searchText || ''}
              onChange={handleSearchChange}
              className="h-10"
            />
          </div>

          {/* Filter Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Severity */}
            <div>
              <Label htmlFor="filter-severity" className="text-sm font-medium mb-2 block">
                Severidade
              </Label>
              <Select
                value={filters.severity || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('severity', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="filter-severity" className="h-10">
                  <SelectValue placeholder="Todas" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas</SelectItem>
                  {SEVERITY_OPTIONS.map((option) => (
                    <SelectItem key={`severity-${option.value}`} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status */}
            <div>
              <Label htmlFor="filter-status" className="text-sm font-medium mb-2 block">
                Status
              </Label>
              <Select
                value={filters.status || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('status', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="filter-status" className="h-10">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  {STATUS_OPTIONS.map((option) => (
                    <SelectItem key={`status-${option.value}`} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Patient */}
            <div>
              <Label htmlFor="filter-patient" className="text-sm font-medium mb-2 block">
                Paciente
              </Label>
              <Select
                value={filters.patientId || 'all'}
                onValueChange={(value: string) =>
                  onFilterChange('patientId', value === 'all' ? undefined : value)
                }
              >
                <SelectTrigger id="filter-patient" className="h-10">
                  <SelectValue placeholder="Todos" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos os pacientes</SelectItem>
                  {patients.map((patient) => (
                    <SelectItem key={`patient-${patient.id}`} value={patient.id}>
                      {patient.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Date Range Compact */}
            <div>
              <Label className="text-sm font-medium mb-2 block">
                Período
              </Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-10 justify-start text-left font-normal w-full"
                  >
                    <Calendar className="mr-2 h-4 w-4" />
                    {filters.dateFrom || filters.dateTo ? (
                      <span className="text-sm">
                        {filters.dateFrom ? new Date(filters.dateFrom).toLocaleDateString('pt-BR') : 'início'} - {filters.dateTo ? new Date(filters.dateTo).toLocaleDateString('pt-BR') : 'hoje'}
                      </span>
                    ) : (
                      'Selecionar período'
                    )}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-72 p-4">
                  <div className="space-y-3">
                    <div>
                      <Label className="text-sm font-medium mb-1.5 block">Data inicial</Label>
                      <Input
                        type="date"
                        value={dateFromValue}
                        onChange={handleDateFromChange}
                        className="h-9"
                      />
                    </div>
                    <div>
                      <Label className="text-sm font-medium mb-1.5 block">Data final</Label>
                      <Input
                        type="date"
                        value={dateToValue}
                        onChange={handleDateToChange}
                        className="h-9"
                      />
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

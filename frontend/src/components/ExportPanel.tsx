import React, { useState } from 'react';
import { ChevronDown, Download, RotateCcw, AlertCircle, Info } from 'lucide-react';
import { exportAlertsToCSV, exportAlertsToPDF, formatDateForExport } from '../lib/exportApi';
import { ApiException } from '../lib/api';
import { Button } from './ui/button';
import { Input } from './ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from './ui/collapsible';
import { RadioGroup, RadioGroupItem } from './ui/radio-group';
import { Label } from './ui/label';
import { Alert, AlertDescription } from './ui/alert';
import { Card } from './ui/card';

interface ExportPanelProps {
  onSuccess?: (message: string) => void;
  onError?: (message: string) => void;
}

export function ExportPanel({ onSuccess, onError }: ExportPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [filters, setFilters] = useState({
    startDate: '',
    endDate: '',
    status: 'all',
    patientId: '',
    format: 'csv' as 'csv' | 'pdf',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasActiveFilters = filters.startDate || filters.endDate || filters.status !== 'all' || filters.patientId;

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
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card className="border-2 border-dashed">
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            className="w-full justify-between px-6 py-4 h-auto hover:bg-muted/50"
          >
            <div className="flex items-center gap-3">
              <Download className="w-5 h-5" />
              <div className="text-left">
                <p className="font-semibold">Exportar Dados</p>
                <p className="text-sm text-muted-foreground">
                  {hasActiveFilters ? `${Object.values(filters).filter(v => v && v !== 'all' && v !== 'csv').length} filtro(s) ativo(s)` : 'Nenhum filtro aplicado'}
                </p>
              </div>
            </div>
            <ChevronDown
              className="w-5 h-5 transition-transform"
              style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)' }}
            />
          </Button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-6 py-4 border-t space-y-4">
            {/* Date Range Section */}
            <div>
              <h4 className="text-sm font-medium mb-3">Período</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="startDate" className="text-xs">
                    Data Inicial
                  </Label>
                  <Input
                    type="date"
                    id="startDate"
                    name="startDate"
                    value={filters.startDate}
                    onChange={handleFilterChange}
                    disabled={loading}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="endDate" className="text-xs">
                    Data Final
                  </Label>
                  <Input
                    type="date"
                    id="endDate"
                    name="endDate"
                    value={filters.endDate}
                    onChange={handleFilterChange}
                    disabled={loading}
                  />
                </div>
              </div>
            </div>

            {/* Filters Section */}
            <div>
              <h4 className="text-sm font-medium mb-3">Filtros</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="status" className="text-xs">
                    Status
                  </Label>
                  <Select
                    value={filters.status}
                    onValueChange={(value: string) =>
                      setFilters(prev => ({ ...prev, status: value }))
                    }
                    disabled={loading}
                  >
                    <SelectTrigger id="status">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos</SelectItem>
                      <SelectItem value="pending">Pendente</SelectItem>
                      <SelectItem value="acknowledged">Reconhecido</SelectItem>
                      <SelectItem value="completed">Concluído</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="patientId" className="text-xs">
                    ID do Paciente
                  </Label>
                  <Input
                    type="text"
                    id="patientId"
                    name="patientId"
                    placeholder="Ex: PAC-0001"
                    value={filters.patientId}
                    onChange={handleFilterChange}
                    disabled={loading}
                  />
                </div>
              </div>
            </div>

            {/* Format Selector */}
            <div>
              <h4 className="text-sm font-medium mb-3">Formato</h4>
              <RadioGroup
                value={filters.format}
                onValueChange={(value) =>
                  setFilters(prev => ({ ...prev, format: value as 'csv' | 'pdf' }))
                }
              >
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="csv" id="csv" disabled={loading} />
                  <Label htmlFor="csv" className="cursor-pointer">
                    CSV
                  </Label>
                </div>
                <div className="flex items-center space-x-2">
                  <RadioGroupItem value="pdf" id="pdf" disabled={loading} />
                  <Label htmlFor="pdf" className="cursor-pointer">
                    PDF
                  </Label>
                </div>
              </RadioGroup>
            </div>

            {/* Error Message */}
            {error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {/* Info Tip */}
            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                Deixe os campos em branco para incluir todos os dados. Use as datas para filtrar por período específico.
              </AlertDescription>
            </Alert>

            {/* Action Buttons */}
            <div className="flex gap-2 pt-2">
              <Button
                onClick={handleExport}
                disabled={loading}
                className="flex-1"
              >
                <Download className="w-4 h-4 mr-2" />
                {loading ? 'Exportando...' : `Baixar ${filters.format.toUpperCase()}`}
              </Button>
              <Button
                variant="outline"
                onClick={handleReset}
                disabled={loading}
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Limpar
              </Button>
            </div>
          </div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}

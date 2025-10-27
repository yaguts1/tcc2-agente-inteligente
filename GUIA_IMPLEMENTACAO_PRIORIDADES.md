# 🛠️ GUIA DE IMPLEMENTAÇÃO - SUGESTÕES PRIORIZADAS

## 📋 Overview

Este documento contém exemplos de código e arquitetura para as **3 principais sugestões críticas**:
1. Filtros Avançados no Dashboard
2. Alertas Visuais para Críticos
3. Bulk Actions para Alertas

---

## 1️⃣ FILTROS AVANÇADOS NO DASHBOARD

### Arquitetura

```
DashboardPage.tsx
├── FilterBar.tsx (novo componente)
│   ├── SeverityFilter
│   ├── StatusFilter
│   ├── DateRangeFilter
│   └── PatientFilter
├── AlertsTable.tsx (adicionar filtragem)
└── useAlertFilters.ts (novo hook)
```

### Implementação

#### 1. Hook: `useAlertFilters.ts`

```typescript
import { useState, useCallback } from 'react';
import { Alert } from '../lib/api';

export interface AlertFilters {
  severity?: ('HIGH' | 'MEDIUM' | 'LOW')[];
  status?: ('pending' | 'acknowledged' | 'completed')[];
  dateRange?: { start: Date; end: Date };
  patientId?: string;
  searchText?: string;
}

export function useAlertFilters() {
  const [filters, setFilters] = useState<AlertFilters>({});
  const [history, setHistory] = useState<AlertFilters[]>([]);

  const applyFilters = useCallback((newFilters: AlertFilters) => {
    setFilters(newFilters);
    setHistory(prev => [...prev.slice(-10), newFilters]); // Keep last 10
  }, []);

  const clearFilters = useCallback(() => {
    setFilters({});
  }, []);

  const filterAlerts = useCallback((alerts: Alert[]): Alert[] => {
    return alerts.filter(alert => {
      // Severity filter
      if (filters.severity && !filters.severity.includes(alert.severity as any)) {
        return false;
      }

      // Status filter
      if (filters.status && !filters.status.includes(alert.status)) {
        return false;
      }

      // Date range filter
      if (filters.dateRange) {
        const alertDate = new Date(alert.ts);
        if (alertDate < filters.dateRange.start || alertDate > filters.dateRange.end) {
          return false;
        }
      }

      // Patient filter
      if (filters.patientId && alert.patient_id !== filters.patientId) {
        return false;
      }

      // Search text
      if (filters.searchText) {
        const searchLower = filters.searchText.toLowerCase();
        const matchesPatient = alert.patient_id.toLowerCase().includes(searchLower);
        const matchesDesc = alert.description?.toLowerCase().includes(searchLower);
        if (!matchesPatient && !matchesDesc) {
          return false;
        }
      }

      return true;
    });
  }, [filters]);

  return {
    filters,
    applyFilters,
    clearFilters,
    filterAlerts,
    filterHistory: history,
  };
}
```

#### 2. Componente: `FilterBar.tsx`

```typescript
import { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Badge } from '../ui/badge';
import { X, Filter } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { AlertFilters } from '../../hooks/useAlertFilters';

interface FilterBarProps {
  filters: AlertFilters;
  onApply: (filters: AlertFilters) => void;
  onClear: () => void;
}

export function FilterBar({ filters, onApply, onClear }: FilterBarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [tempFilters, setTempFilters] = useState<AlertFilters>(filters);

  const handleApply = () => {
    onApply(tempFilters);
    setShowAdvanced(false);
  };

  const activeFilterCount = Object.values(filters).filter(
    v => v !== undefined && (Array.isArray(v) ? v.length > 0 : true)
  ).length;

  return (
    <div className="space-y-4">
      {/* Quick Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <Input
          placeholder="Buscar por paciente ou descrição..."
          value={tempFilters.searchText || ''}
          onChange={(e) =>
            setTempFilters(prev => ({ ...prev, searchText: e.target.value }))
          }
          className="flex-1 min-w-64"
        />

        <Button
          variant={showAdvanced ? 'default' : 'outline'}
          size="sm"
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <Filter className="w-4 h-4 mr-2" />
          Filtros Avançados
          {activeFilterCount > 0 && (
            <Badge className="ml-2" variant="secondary">
              {activeFilterCount}
            </Badge>
          )}
        </Button>

        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              onClear();
              setTempFilters({});
            }}
          >
            <X className="w-4 h-4 mr-1" />
            Limpar
          </Button>
        )}
      </div>

      {/* Advanced Filters */}
      {showAdvanced && (
        <div className="border border-border rounded-lg p-4 space-y-4 bg-surface">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Severity Filter */}
            <div>
              <label className="text-sm font-medium mb-2 block">Severidade</label>
              <div className="space-y-2">
                {(['HIGH', 'MEDIUM', 'LOW'] as const).map(level => (
                  <label key={level} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={tempFilters.severity?.includes(level) || false}
                      onChange={(e) => {
                        const current = tempFilters.severity || [];
                        if (e.target.checked) {
                          setTempFilters(prev => ({
                            ...prev,
                            severity: [...current, level]
                          }));
                        } else {
                          setTempFilters(prev => ({
                            ...prev,
                            severity: current.filter(s => s !== level)
                          }));
                        }
                      }}
                      className="rounded"
                    />
                    <span className="text-sm">{level}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Status Filter */}
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <div className="space-y-2">
                {(['pending', 'acknowledged', 'completed'] as const).map(status => (
                  <label key={status} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={tempFilters.status?.includes(status) || false}
                      onChange={(e) => {
                        const current = tempFilters.status || [];
                        if (e.target.checked) {
                          setTempFilters(prev => ({
                            ...prev,
                            status: [...current, status]
                          }));
                        } else {
                          setTempFilters(prev => ({
                            ...prev,
                            status: current.filter(s => s !== status)
                          }));
                        }
                      }}
                      className="rounded"
                    />
                    <span className="text-sm capitalize">{status}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Date Range */}
            <div>
              <label className="text-sm font-medium mb-2 block">Data Inicial</label>
              <input
                type="date"
                value={tempFilters.dateRange?.start?.toISOString().split('T')[0] || ''}
                onChange={(e) => {
                  const newStart = new Date(e.target.value);
                  setTempFilters(prev => ({
                    ...prev,
                    dateRange: {
                      start: newStart,
                      end: prev.dateRange?.end || new Date()
                    }
                  }));
                }}
                className="w-full px-3 py-2 border rounded-lg"
              />
            </div>

            <div>
              <label className="text-sm font-medium mb-2 block">Data Final</label>
              <input
                type="date"
                value={tempFilters.dateRange?.end?.toISOString().split('T')[0] || ''}
                onChange={(e) => {
                  const newEnd = new Date(e.target.value);
                  setTempFilters(prev => ({
                    ...prev,
                    dateRange: {
                      start: prev.dateRange?.start || new Date(),
                      end: newEnd
                    }
                  }));
                }}
                className="w-full px-3 py-2 border rounded-lg"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setShowAdvanced(false);
                setTempFilters(filters);
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleApply}>
              Aplicar Filtros
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

#### 3. Atualizar `DashboardPage.tsx`

```typescript
import { useAlertFilters } from '../../hooks/useAlertFilters';
import { FilterBar } from '../shared/FilterBar';

export function DashboardPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const { filters, applyFilters, clearFilters, filterAlerts } = useAlertFilters();

  // ... existing code ...

  const filteredAlerts = filterAlerts(alerts);

  return (
    <div className="space-y-6">
      {/* ... existing header ... */}

      <FilterBar
        filters={filters}
        onApply={applyFilters}
        onClear={clearFilters}
      />

      <Card>
        <AlertsTable
          alerts={filteredAlerts}
          onAcknowledge={handleAcknowledge}
          onComplete={handleComplete}
        />
      </Card>

      {filteredAlerts.length === 0 && alerts.length > 0 && (
        <EmptyState
          icon={Filter}
          title="Nenhum alerta encontrado"
          description="Tente ajustar os filtros para encontrar o que procura"
        />
      )}
    </div>
  );
}
```

---

## 2️⃣ ALERTAS VISUAIS PARA CRÍTICOS

### Arquitetura

```
AppLayout.tsx
├── CriticalAlertBadge (novo)
└── useDesktopNotifications (novo hook)

DashboardPage.tsx
├── useCriticalAlerts (novo hook)
└── Integração com notificações
```

### Implementação

#### 1. Hook: `useCriticalAlerts.ts`

```typescript
import { useEffect, useCallback } from 'react';
import { Alert } from '../lib/api';

export function useCriticalAlerts() {
  const getCriticalCount = useCallback((alerts: Alert[]): number => {
    return alerts.filter(a => a.severity === 'HIGH' && a.status === 'pending').length;
  }, []);

  const playAlertSound = useCallback(() => {
    // Usar Web Audio API para tocar som
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = 800;
    oscillator.type = 'sine';

    gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.5);
  }, []);

  const showDesktopNotification = useCallback((options: {
    title: string;
    body: string;
    icon?: string;
    tag?: string;
    requireInteraction?: boolean;
  }) => {
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(options.title, {
        body: options.body,
        icon: options.icon || '/alert-icon.png',
        tag: options.tag || 'alert',
        requireInteraction: options.requireInteraction || false,
      });
    }
  }, []);

  const requestNotificationPermission = useCallback(async () => {
    if ('Notification' in window && Notification.permission === 'default') {
      const permission = await Notification.requestPermission();
      return permission === 'granted';
    }
    return Notification.permission === 'granted';
  }, []);

  return {
    getCriticalCount,
    playAlertSound,
    showDesktopNotification,
    requestNotificationPermission,
  };
}
```

#### 2. Componente: `CriticalAlertBadge.tsx`

```typescript
import { Bell } from 'lucide-react';
import { Badge } from '../ui/badge';
import { cn } from '../ui/utils';

interface CriticalAlertBadgeProps {
  count: number;
  onClick?: () => void;
}

export function CriticalAlertBadge({ count, onClick }: CriticalAlertBadgeProps) {
  if (count === 0) return null;

  return (
    <button
      onClick={onClick}
      className={cn(
        'relative p-2 hover:bg-surface rounded-lg transition-colors',
        count > 0 && 'animate-pulse'
      )}
    >
      <Bell className="w-5 h-5 text-destructive" />
      <Badge
        className="absolute -top-1 -right-1 bg-destructive text-destructive-foreground"
        variant="default"
      >
        {count > 99 ? '99+' : count}
      </Badge>
    </button>
  );
}
```

#### 3. Integração em `AppLayout.tsx`

```typescript
import { useEffect, useState } from 'react';
import { useCriticalAlerts } from '../../hooks/useCriticalAlerts';
import { CriticalAlertBadge } from '../alerts/CriticalAlertBadge';

export function AppLayout({ children, ...props }: AppLayoutProps) {
  const { getCriticalCount, playAlertSound, showDesktopNotification, requestNotificationPermission } = useCriticalAlerts();
  const [criticalCount, setCriticalCount] = useState(0);
  const [lastCount, setLastCount] = useState(0);

  // Exemplo: chamar isso quando alerts mudam
  const handleAlertsUpdate = (alerts: Alert[]) => {
    const newCount = getCriticalCount(alerts);
    setCriticalCount(newCount);

    // Se chegou novo alerta crítico
    if (newCount > lastCount) {
      const newAlerts = newCount - lastCount;
      playAlertSound();
      showDesktopNotification({
        title: '🚨 Alerta Crítico!',
        body: `${newAlerts} novo(s) alerta(s) de alto risco requerem ação imediata`,
        requireInteraction: true,
      });
    }

    setLastCount(newCount);
  };

  useEffect(() => {
    // Pedir permissão de notificação ao carregar
    requestNotificationPermission();
  }, [requestNotificationPermission]);

  return (
    <div className="min-h-screen bg-bg">
      {/* ... existing code ... */}

      {/* Desktop Header - Adicionar Badge */}
      <div className="hidden lg:flex items-center gap-2 px-6 py-5 border-b border-border">
        {/* ... existing items ... */}

        <CriticalAlertBadge
          count={criticalCount}
          onClick={() => {
            // Rolar para alertas críticos
            const element = document.querySelector('[data-critical-alerts]');
            element?.scrollIntoView({ behavior: 'smooth' });
          }}
        />
      </div>

      {/* ... rest of layout ... */}
    </div>
  );
}
```

---

## 3️⃣ BULK ACTIONS PARA ALERTAS

### Arquitetura

```
AlertsTable.tsx (atualizar)
├── SelectionCheckbox
├── BulkActionBar (novo)
└── useAlertSelection (novo hook)
```

### Implementação

#### 1. Hook: `useAlertSelection.ts`

```typescript
import { useState, useCallback } from 'react';
import { Alert } from '../lib/api';

export function useAlertSelection() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  }, []);

  const selectAll = useCallback((alerts: Alert[]) => {
    setSelectedIds(new Set(alerts.map(a => a.id)));
  }, []);

  const deselectAll = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const toggleSelectAll = useCallback((alerts: Alert[]) => {
    if (selectedIds.size === alerts.length) {
      deselectAll();
    } else {
      selectAll(alerts);
    }
  }, [selectedIds.size, selectAll, deselectAll]);

  const getSelected = useCallback((alerts: Alert[]): Alert[] => {
    return alerts.filter(a => selectedIds.has(a.id));
  }, [selectedIds]);

  return {
    selectedIds,
    toggleSelect,
    selectAll,
    deselectAll,
    toggleSelectAll,
    getSelected,
    selectedCount: selectedIds.size,
  };
}
```

#### 2. Componente: `BulkActionBar.tsx`

```typescript
import { useState } from 'react';
import { Button } from '../ui/button';
import { Alert, alertsApi, ApiException } from '../../lib/api';
import { Eye, Check, Download, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '../ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';

interface BulkActionBarProps {
  selectedCount: number;
  selectedAlerts: Alert[];
  onClear: () => void;
  onSuccess: () => void;
}

export function BulkActionBar({
  selectedCount,
  selectedAlerts,
  onClear,
  onSuccess,
}: BulkActionBarProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [action, setAction] = useState<string | null>(null);

  const handleBulkAction = async (actionType: string) => {
    setIsLoading(true);
    try {
      const ids = selectedAlerts.map(a => a.id);

      switch (actionType) {
        case 'acknowledge':
          await Promise.all(ids.map(id => alertsApi.acknowledge(id)));
          toast.success(`${ids.length} alerta(s) reconhecido(s)`);
          break;

        case 'complete':
          await Promise.all(ids.map(id => alertsApi.complete(id)));
          toast.success(`${ids.length} alerta(s) completado(s)`);
          break;

        case 'export':
          const csvContent = [
            ['ID', 'Paciente', 'Severidade', 'Status', 'Data'].join(','),
            ...selectedAlerts.map(a =>
              [a.id, a.patient_id, a.severity, a.status, a.ts].join(',')
            ),
          ].join('\n');

          const blob = new Blob([csvContent], { type: 'text/csv' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `alertas-${new Date().toISOString().split('T')[0]}.csv`;
          a.click();
          toast.success('Alertas exportados em CSV');
          break;

        case 'delete':
          await Promise.all(ids.map(id => alertsApi.deleteAlert(id)));
          toast.success(`${ids.length} alerta(s) deletado(s)`);
          break;
      }

      onSuccess();
      onClear();
    } catch (err) {
      if (err instanceof ApiException) {
        toast.error(err.message);
      } else {
        toast.error('Erro ao executar ação em lote');
      }
    } finally {
      setIsLoading(false);
      setAction(null);
    }
  };

  if (selectedCount === 0) return null;

  return (
    <>
      <div className="fixed bottom-0 left-0 right-0 bg-surface border-t border-border p-4 flex items-center justify-between gap-4 z-40">
        <div className="flex items-center gap-3">
          <Badge variant="secondary" className="text-base">
            {selectedCount} selecionado{selectedCount !== 1 ? 's' : ''}
          </Badge>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setAction('acknowledge');
              handleBulkAction('acknowledge');
            }}
            disabled={isLoading}
          >
            <Eye className="w-4 h-4 mr-2" />
            Reconhecer
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setAction('complete');
              handleBulkAction('complete');
            }}
            disabled={isLoading}
          >
            <Check className="w-4 h-4 mr-2" />
            Completar
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={() => handleBulkAction('export')}
            disabled={isLoading}
          >
            <Download className="w-4 h-4 mr-2" />
            Exportar
          </Button>

          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              setAction('delete');
              setShowConfirm(true);
            }}
            disabled={isLoading}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Deletar
          </Button>

          <Button
            size="sm"
            variant="ghost"
            onClick={onClear}
            disabled={isLoading}
          >
            <X className="w-4 h-4 mr-2" />
            Cancelar
          </Button>
        </div>
      </div>

      {/* Confirm Delete Dialog */}
      <AlertDialog open={showConfirm} onOpenChange={setShowConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deletar alertas?</AlertDialogTitle>
            <AlertDialogDescription>
              Você tem certeza que deseja deletar {selectedCount} alerta(s)? Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                handleBulkAction('delete');
                setShowConfirm(false);
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Deletar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
```

#### 3. Atualizar `AlertsTable.tsx`

```typescript
import { useAlertSelection } from '../../hooks/useAlertSelection';
import { BulkActionBar } from '../alerts/BulkActionBar';
import { Checkbox } from '../ui/checkbox';

export function AlertsTable({ alerts, onAcknowledge, onComplete }: AlertsTableProps) {
  const { selectedIds, toggleSelect, toggleSelectAll, getSelected, deselectAll } = useAlertSelection();
  const selectedAlerts = getSelected(alerts);

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-3 text-left">
                <Checkbox
                  checked={selectedIds.size === alerts.length && alerts.length > 0}
                  indeterminate={selectedIds.size > 0 && selectedIds.size < alerts.length}
                  onChange={() => toggleSelectAll(alerts)}
                />
              </th>
              <th className="px-4 py-3 text-left text-sm font-medium">Paciente</th>
              <th className="px-4 py-3 text-left text-sm font-medium">Severidade</th>
              <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
              <th className="px-4 py-3 text-left text-sm font-medium">Data</th>
              <th className="px-4 py-3 text-right text-sm font-medium">Ações</th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((alert) => (
              <tr
                key={alert.id}
                className={cn(
                  'border-b border-border hover:bg-muted transition-colors',
                  selectedIds.has(alert.id) && 'bg-primary/10'
                )}
              >
                <td className="px-4 py-3">
                  <Checkbox
                    checked={selectedIds.has(alert.id)}
                    onChange={() => toggleSelect(alert.id)}
                  />
                </td>
                {/* ... existing cells ... */}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <BulkActionBar
        selectedCount={selectedIds.size}
        selectedAlerts={selectedAlerts}
        onClear={deselectAll}
        onSuccess={() => {
          // Recarregar alertas
        }}
      />
    </>
  );
}
```

---

## 📊 Checklist de Implementação

### Filtros Avançados
- [ ] Criar hook `useAlertFilters`
- [ ] Criar componente `FilterBar`
- [ ] Integrar em `DashboardPage`
- [ ] Testar com diferentes combinações de filtros
- [ ] Salvar filtros no localStorage
- [ ] Docs: Como usar filtros

### Alertas Críticos
- [ ] Criar hook `useCriticalAlerts`
- [ ] Criar componente `CriticalAlertBadge`
- [ ] Integrar em `AppLayout`
- [ ] Configurar som de alerta
- [ ] Testar notificações desktop
- [ ] Docs: Como ativar notificações

### Bulk Actions
- [ ] Criar hook `useAlertSelection`
- [ ] Criar componente `BulkActionBar`
- [ ] Atualizar `AlertsTable`
- [ ] Implementar ações (acknowledge, complete, export, delete)
- [ ] Testar confirmações
- [ ] Docs: Como usar bulk actions

---

## 🧪 Testes Sugeridos

```typescript
// FilterBar.test.tsx
describe('FilterBar', () => {
  it('should filter alerts by severity', () => {
    render(<FilterBar filters={{}} onApply={mock} onClear={mock} />);
    userEvent.click(screen.getByText('Filtros Avançados'));
    userEvent.click(screen.getByLabelText('HIGH'));
    userEvent.click(screen.getByText('Aplicar Filtros'));
    expect(mock).toHaveBeenCalledWith({ severity: ['HIGH'] });
  });
});

// useAlertSelection.test.ts
describe('useAlertSelection', () => {
  it('should toggle select alerts', () => {
    const { result } = renderHook(() => useAlertSelection());
    act(() => result.current.toggleSelect('alert-1'));
    expect(result.current.selectedIds.has('alert-1')).toBe(true);
  });
});
```

---

## 📈 Impacto Esperado

| Feature | Produtividade | Performance | UX | Impacto |
|---------|---|---|---|---|
| Filtros | +40% | +5% | ⭐⭐⭐⭐⭐ | Crítico |
| Alertas Críticos | +20% | Neutro | ⭐⭐⭐⭐⭐ | Alto |
| Bulk Actions | +35% | +10% | ⭐⭐⭐⭐ | Alto |

**Total Estimado**: +95% produtividade, ~15-20 horas de desenvolvimento

---

*Documento gerado em: 27/10/2025*

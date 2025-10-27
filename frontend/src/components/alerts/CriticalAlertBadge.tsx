import React, { useEffect, useState } from 'react';
import { AlertTriangle, Bell } from 'lucide-react';
import { Badge } from '../ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '../ui/popover';
import { Card } from '../ui/card';
import { CriticalAlert } from '../../hooks/useCriticalAlerts';

interface CriticalAlertBadgeProps {
  totalCritical: number;
  highRisk: number;
  acknowledgedMedium: number;
  hasNewCritical: boolean;
  criticalAlerts: CriticalAlert[];
  onAlertClick?: (alert: CriticalAlert) => void;
}

export function CriticalAlertBadge({
  totalCritical,
  highRisk,
  acknowledgedMedium,
  hasNewCritical,
  criticalAlerts,
  onAlertClick,
}: CriticalAlertBadgeProps) {
  const [pulseAnimation, setPulseAnimation] = useState(false);

  // Trigger pulse animation when new critical alerts
  useEffect(() => {
    if (hasNewCritical) {
      setPulseAnimation(true);
      const timer = setTimeout(() => setPulseAnimation(false), 5000);
      return () => clearTimeout(timer);
    }
  }, [hasNewCritical]);

  if (totalCritical === 0) {
    return null;
  }

  const pulseClass = pulseAnimation ? 'animate-pulse' : '';

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className={`relative ${pulseClass}`}>
          <Badge
            variant="destructive"
            className="flex items-center gap-1.5 py-2 px-3 text-xs font-semibold cursor-pointer hover:bg-red-700"
          >
            <AlertTriangle className="w-4 h-4" />
            <span>{totalCritical}</span>
          </Badge>
          {hasNewCritical && (
            <span className="absolute -top-2 -right-2 w-4 h-4 bg-red-500 rounded-full animate-bounce" />
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-80 p-0">
        <div className="divide-y">
          {/* Header */}
          <div className="p-4 bg-red-50">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <h3 className="font-semibold text-red-900">Alertas Críticos</h3>
            </div>
            <p className="text-sm text-red-700">
              {totalCritical} alerta{totalCritical !== 1 ? 's' : ''} crítico{totalCritical !== 1 ? 's' : ''}
            </p>
          </div>

          {/* Summary */}
          <div className="p-4 bg-gray-50">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="bg-white p-2 rounded border border-red-200">
                <p className="text-gray-600">Risco Alto</p>
                <p className="text-lg font-bold text-red-600">{highRisk}</p>
              </div>
              <div className="bg-white p-2 rounded border border-yellow-200">
                <p className="text-gray-600">Médio (Reconh.)</p>
                <p className="text-lg font-bold text-yellow-600">{acknowledgedMedium}</p>
              </div>
            </div>
          </div>

          {/* Critical Alerts List */}
          {criticalAlerts.length > 0 && (
            <div className="max-h-96 overflow-y-auto">
              {criticalAlerts.map((alert) => (
                <div
                  key={alert.id}
                  onClick={() => onAlertClick?.(alert)}
                  className="p-3 border-b last:border-b-0 hover:bg-gray-50 cursor-pointer transition-colors"
                >
                  <div className="flex items-start gap-2">
                    <div
                      className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${
                        alert.riskLevel === 'high'
                          ? 'bg-red-600'
                          : 'bg-yellow-600'
                      }`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm text-gray-900 truncate">
                        {alert.patientName}
                      </p>
                      <p className="text-xs text-gray-600 mt-1">
                        Sala: {alert.room} | Leito: {alert.bed}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Status:{' '}
                        <span
                          className={
                            alert.status === 'acknowledged'
                              ? 'text-yellow-600 font-medium'
                              : 'text-red-600 font-medium'
                          }
                        >
                          {alert.status === 'acknowledged'
                            ? 'Reconhecido'
                            : 'Pendente'}
                        </span>
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        Próximo: {new Date(alert.nextRepositioning).toLocaleTimeString('pt-BR')}
                      </p>
                    </div>
                    {alert.isNew && (
                      <div className="flex-shrink-0">
                        <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
                          <Bell className="w-3 h-3" />
                          Novo
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Empty State */}
          {criticalAlerts.length === 0 && (
            <div className="p-6 text-center text-gray-500">
              <p className="text-sm">Nenhum alerta crítico no momento</p>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

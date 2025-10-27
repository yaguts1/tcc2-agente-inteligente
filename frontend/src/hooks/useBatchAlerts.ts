import { useState, useCallback } from 'react';
import { alertsApi } from '../lib/api';
import { toast } from 'sonner';

interface BatchResult {
  ok: boolean;
  processed: number;
  failed: number;
  errors: Array<{ alert_id: string; error: string }>;
}

export function useBatchAlerts() {
  const [isProcessing, setIsProcessing] = useState(false);

  const batchAcknowledge = useCallback(
    async (alertIds: string[]): Promise<BatchResult | null> => {
      if (alertIds.length === 0) {
        toast.warning('Selecione pelo menos um alerta');
        return null;
      }

      setIsProcessing(true);
      try {
        const result = await alertsApi.batchAcknowledge(alertIds);
        
        if (result.ok) {
          toast.success(`${result.processed} alerta(s) reconhecido(s)`);
          if (result.failed > 0) {
            toast.warning(`${result.failed} alerta(s) falharam`);
          }
        }
        
        return result;
      } catch (err) {
        toast.error('Erro ao reconhecer alertas em lote');
        console.error('Batch acknowledge error:', err);
        return null;
      } finally {
        setIsProcessing(false);
      }
    },
    []
  );

  const batchComplete = useCallback(
    async (alertIds: string[]): Promise<BatchResult | null> => {
      if (alertIds.length === 0) {
        toast.warning('Selecione pelo menos um alerta');
        return null;
      }

      setIsProcessing(true);
      try {
        const result = await alertsApi.batchComplete(alertIds);
        
        if (result.ok) {
          toast.success(`${result.processed} paciente(s) reposicionado(s)`);
          if (result.failed > 0) {
            toast.warning(`${result.failed} alerta(s) falharam`);
          }
        }
        
        return result;
      } catch (err) {
        toast.error('Erro ao completar alertas em lote');
        console.error('Batch complete error:', err);
        return null;
      } finally {
        setIsProcessing(false);
      }
    },
    []
  );

  return {
    batchAcknowledge,
    batchComplete,
    isProcessing,
  };
}

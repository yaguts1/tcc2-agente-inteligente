import { useState } from 'react';
import { patientsApi, SimulationRequest, SimulationResult, ApiException } from '../lib/api';

interface UseSimulationState {
  isLoading: boolean;
  error: string | null;
  result: SimulationResult | null;
}

export function useSimulation(patientId: string) {
  const [state, setState] = useState<UseSimulationState>({
    isLoading: false,
    error: null,
    result: null,
  });

  const simulate = async (params: SimulationRequest) => {
    setState({ isLoading: true, error: null, result: null });

    try {
      // Validar parâmetros
      if (params.duracao_horas < 1 || params.duracao_horas > 72) {
        throw new Error('Duração deve estar entre 1 e 72 horas');
      }

      if (!['baixo', 'medio', 'alto'].includes(params.perfil)) {
        throw new Error('Perfil inválido');
      }

      const result = await patientsApi.simulateData(patientId, params);

      if (!result.success) {
        throw new Error(result.error || result.message || 'Erro ao simular');
      }

      setState({ isLoading: false, error: null, result });
      return result;
    } catch (err) {
      let errorMessage = 'Erro ao gerar dados simulados';

      if (err instanceof ApiException) {
        errorMessage = err.message;
      } else if (err instanceof Error) {
        errorMessage = err.message;
      }

      setState({ isLoading: false, error: errorMessage, result: null });
      throw err;
    }
  };

  const reset = () => {
    setState({ isLoading: false, error: null, result: null });
  };

  return {
    ...state,
    simulate,
    reset,
  };
}

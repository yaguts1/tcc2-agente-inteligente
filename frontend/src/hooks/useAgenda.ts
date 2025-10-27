/**
 * Hook para gerenciar agendas de paciente
 * Fornece estado e funções para CRUD de agendas
 */

import { useState, useCallback, useEffect } from "react";
import AgendaApi, { Agenda, AgendaCreate, AgendaUpdate } from "../api/agendaApi";

interface UseAgendaState {
  agendas: Agenda[];
  loading: boolean;
  error: string | null;
  selectedAgenda: Agenda | null;
}

interface UseAgendaActions {
  loadAgendas: (ativo?: boolean) => Promise<void>;
  createAgenda: (data: AgendaCreate) => Promise<Agenda>;
  updateAgenda: (agendaId: number, data: AgendaUpdate) => Promise<Agenda>;
  deleteAgenda: (agendaId: number) => Promise<void>;
  selectAgenda: (agenda: Agenda | null) => void;
  clearError: () => void;
}

type UseAgendaReturn = UseAgendaState & UseAgendaActions;

export function useAgenda(pacienteId: string): UseAgendaReturn {
  const [state, setState] = useState<UseAgendaState>({
    agendas: [],
    loading: false,
    error: null,
    selectedAgenda: null,
  });

  // Load agendas on mount or when pacienteId changes
  useEffect(() => {
    if (pacienteId) {
      loadAgendas();
    }
  }, [pacienteId]);

  const loadAgendas = useCallback(
    async (ativo?: boolean) => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const response = await AgendaApi.listAgendas(pacienteId, ativo);
        setState((prev) => ({
          ...prev,
          agendas: response.agendas,
          loading: false,
        }));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Erro ao carregar agendas";
        setState((prev) => ({
          ...prev,
          loading: false,
          error: message,
        }));
      }
    },
    [pacienteId]
  );

  const createAgenda = useCallback(
    async (data: AgendaCreate): Promise<Agenda> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const agenda = await AgendaApi.createAgenda(pacienteId, data);
        setState((prev) => ({
          ...prev,
          agendas: Array.isArray(prev.agendas) ? [...prev.agendas, agenda] : [agenda],
          loading: false,
        }));
        return agenda;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Erro ao criar agenda";
        setState((prev) => ({
          ...prev,
          loading: false,
          error: message,
        }));
        throw error;
      }
    },
    [pacienteId]
  );

  const updateAgenda = useCallback(
    async (agendaId: number, data: AgendaUpdate): Promise<Agenda> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const updated = await AgendaApi.updateAgenda(
          pacienteId,
          agendaId,
          data
        );
        setState((prev) => ({
          ...prev,
          agendas: Array.isArray(prev.agendas)
            ? prev.agendas.map((a) => (a.id === agendaId ? updated : a))
            : [updated],
          selectedAgenda:
            prev.selectedAgenda?.id === agendaId ? updated : prev.selectedAgenda,
          loading: false,
        }));
        return updated;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Erro ao atualizar agenda";
        setState((prev) => ({
          ...prev,
          loading: false,
          error: message,
        }));
        throw error;
      }
    },
    [pacienteId]
  );

  const deleteAgenda = useCallback(
    async (agendaId: number): Promise<void> => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        await AgendaApi.deleteAgenda(pacienteId, agendaId);
        setState((prev) => ({
          ...prev,
          agendas: Array.isArray(prev.agendas)
            ? prev.agendas.filter((a) => a.id !== agendaId)
            : [],
          selectedAgenda:
            prev.selectedAgenda?.id === agendaId ? null : prev.selectedAgenda,
          loading: false,
        }));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Erro ao deletar agenda";
        setState((prev) => ({
          ...prev,
          loading: false,
          error: message,
        }));
        throw error;
      }
    },
    [pacienteId]
  );

  const selectAgenda = useCallback((agenda: Agenda | null) => {
    setState((prev) => ({
      ...prev,
      selectedAgenda: agenda,
    }));
  }, []);

  const clearError = useCallback(() => {
    setState((prev) => ({
      ...prev,
      error: null,
    }));
  }, []);

  return {
    ...state,
    loadAgendas,
    createAgenda,
    updateAgenda,
    deleteAgenda,
    selectAgenda,
    clearError,
  };
}

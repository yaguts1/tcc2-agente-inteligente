/**
 * API client para Sistema de Agenda
 * Gerencia requisições CRUD de agendas para pacientes
 */

interface AgendaCreate {
  tipo: "refeicao" | "cirurgia" | "procedimento" | "atendimento" | "outro";
  modo: "suprimir" | "reduzir" | "monitorar";
  hora_inicio: string; // HH:MM
  hora_fim: string; // HH:MM
  dias_semana?: number[] | null; // [0-6] ou null para one-time
  data_inicio: string; // YYYY-MM-DD
  data_fim?: string | null; // YYYY-MM-DD ou null
  reducao_janela_min?: number | null; // 5-60
  descricao?: string;
}

interface AgendaUpdate {
  tipo?: string;
  modo?: string;
  hora_inicio?: string;
  hora_fim?: string;
  dias_semana?: number[] | null;
  data_inicio?: string;
  data_fim?: string | null;
  reducao_janela_min?: number | null;
  descricao?: string;
}

interface Agenda extends AgendaCreate {
  id: number;
  paciente_id: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

interface SuppressionCheckResponse {
  em_periodo_suprimido: boolean;
  modo_resultado: "suprimir" | "reduzir" | "monitorar" | null;
  agendas_ativas: number[];
}

interface AgendasResponse {
  agendas: Agenda[];
  total: number;
}

const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

class AgendaApi {
  /**
   * Cria uma nova agenda para paciente
   */
  static async createAgenda(
    pacienteId: string,
    data: AgendaCreate
  ): Promise<Agenda> {
    const response = await fetch(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
        credentials: "include",
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Erro ao criar agenda");
    }

    return response.json();
  }

  /**
   * Lista agendas do paciente
   */
  static async listAgendas(
    pacienteId: string,
    ativo?: boolean
  ): Promise<AgendasResponse> {
    const url = new URL(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda`
    );

    if (ativo !== undefined) {
      url.searchParams.append("ativo", String(ativo));
    }

    const response = await fetch(url.toString(), {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error("Erro ao listar agendas");
    }

    // Backend retorna array diretamente, converter para formato esperado
    const agendas = await response.json();
    return {
      agendas: Array.isArray(agendas) ? agendas : [],
      total: Array.isArray(agendas) ? agendas.length : 0,
    };
  }

  /**
   * Obtém agenda específica
   */
  static async getAgenda(
    pacienteId: string,
    agendaId: number
  ): Promise<Agenda> {
    const response = await fetch(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda/${agendaId}`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new Error("Erro ao obter agenda");
    }

    return response.json();
  }

  /**
   * Atualiza agenda (campos opcionais)
   */
  static async updateAgenda(
    pacienteId: string,
    agendaId: number,
    data: AgendaUpdate
  ): Promise<Agenda> {
    const response = await fetch(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda/${agendaId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(data),
        credentials: "include",
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Erro ao atualizar agenda");
    }

    return response.json();
  }

  /**
   * Deleta agenda (soft delete)
   */
  static async deleteAgenda(
    pacienteId: string,
    agendaId: number
  ): Promise<void> {
    const response = await fetch(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda/${agendaId}`,
      {
        method: "DELETE",
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new Error("Erro ao deletar agenda");
    }
  }

  /**
   * Verifica se timestamp está em período suprimido
   */
  static async checkSuppression(
    pacienteId: string,
    timestamp: string
  ): Promise<SuppressionCheckResponse> {
    const url = new URL(
      `${API_BASE}/api/pacientes/${pacienteId}/agenda/check`
    );
    url.searchParams.append("timestamp", timestamp);

    const response = await fetch(url.toString(), {
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error("Erro ao verificar supressão");
    }

    return response.json();
  }
}

export default AgendaApi;
export type {
  Agenda,
  AgendaCreate,
  AgendaUpdate,
  SuppressionCheckResponse,
  AgendasResponse,
};

/**
 * AgendaList Component
 * Lista de agendas com ações (edit, delete)
 */

import React from "react";
import { Agenda } from "../../api/agendaApi";
import "./AgendaList.css";

interface AgendaListProps {
  agendas: Agenda[];
  loading: boolean;
  onEdit: (agenda: Agenda) => void;
  onDelete: (agendaId: number) => Promise<void>;
}

const AGENDA_TYPE_LABELS: Record<string, string> = {
  refeicao: "Refeição",
  cirurgia: "Cirurgia",
  procedimento: "Procedimento",
  atendimento: "Atendimento",
  outro: "Outro",
};

const MODE_LABELS: Record<string, string> = {
  suprimir: "Suprimir",
  reduzir: "Reduzir",
  monitorar: "Monitorar",
};

const MODE_COLORS: Record<string, string> = {
  suprimir: "#dc3545",
  reduzir: "#ffc107",
  monitorar: "#17a2b8",
};

const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"];

const formatDateRange = (dataInicio: string, dataFim?: string | null): string => {
  const inicio = new Date(dataInicio).toLocaleDateString("pt-BR");
  if (!dataFim) return inicio;
  const fim = new Date(dataFim).toLocaleDateString("pt-BR");
  return `${inicio} até ${fim}`;
};

const formatWeekdays = (dias: number[]): string => {
  if (!dias || dias.length === 0) return "-";
  if (dias.length === 7) return "Todos os dias";
  if (dias.length === 5 && dias.every((d) => d < 5)) return "Seg-Sex";
  return dias.map((d) => WEEKDAY_LABELS[d]).join(", ");
};

export const AgendaList: React.FC<AgendaListProps> = ({
  agendas,
  loading,
  onEdit,
  onDelete,
}) => {
  const [deleting, setDeleting] = React.useState<number | null>(null);

  const handleDelete = async (agendaId: number) => {
    if (!confirm("Tem certeza que deseja deletar esta agenda?")) return;

    try {
      setDeleting(agendaId);
      await onDelete(agendaId);
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return <div className="agenda-list__loading">Carregando agendas...</div>;
  }

  if (!agendas || agendas.length === 0) {
    return (
      <div className="agenda-list__empty">
        <p>Nenhuma agenda cadastrada</p>
        <p className="agenda-list__empty-hint">
          Crie uma agenda para suprimir, reduzir ou monitorar alertas
        </p>
      </div>
    );
  }

  return (
    <div className="agenda-list">
      <div className="agenda-list__grid">
        {agendas.map((agenda) => (
          <div key={agenda.id} className="agenda-list__card">
            <div className="agenda-list__card-header">
              <div>
                <h3 className="agenda-list__type">
                  {AGENDA_TYPE_LABELS[agenda.tipo]}
                </h3>
                <p className="agenda-list__description">{agenda.descricao}</p>
              </div>
              <span
                className="agenda-list__mode-badge"
                style={{ backgroundColor: MODE_COLORS[agenda.modo] }}
              >
                {MODE_LABELS[agenda.modo]}
              </span>
            </div>

            <div className="agenda-list__card-body">
              {/* Horário */}
              <div className="agenda-list__field">
                <span className="agenda-list__label">Horário:</span>
                <span className="agenda-list__value">
                  {agenda.hora_inicio} - {agenda.hora_fim}
                </span>
              </div>

              {/* Dias/Data */}
              <div className="agenda-list__field">
                <span className="agenda-list__label">
                  {agenda.dias_semana ? "Dias:" : "Data:"}
                </span>
                <span className="agenda-list__value">
                  {agenda.dias_semana
                    ? formatWeekdays(agenda.dias_semana)
                    : formatDateRange(agenda.data_inicio, agenda.data_fim)}
                </span>
              </div>

              {/* Redução (se aplicável) */}
              {agenda.reducao_janela_min && (
                <div className="agenda-list__field">
                  <span className="agenda-list__label">Redução:</span>
                  <span className="agenda-list__value">
                    {agenda.reducao_janela_min} minutos
                  </span>
                </div>
              )}

              {/* Status */}
              <div className="agenda-list__field">
                <span className="agenda-list__label">Status:</span>
                <span className={`agenda-list__status ${agenda.ativo ? "active" : "inactive"}`}>
                  {agenda.ativo ? "Ativa" : "Inativa"}
                </span>
              </div>
            </div>

            {/* Ações */}
            <div className="agenda-list__card-footer">
              <button
                className="agenda-list__btn agenda-list__btn--edit"
                onClick={() => onEdit(agenda)}
                disabled={loading}
              >
                Editar
              </button>
              <button
                className="agenda-list__btn agenda-list__btn--delete"
                onClick={() => handleDelete(agenda.id)}
                disabled={loading || deleting === agenda.id}
              >
                {deleting === agenda.id ? "Deletando..." : "Deletar"}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AgendaList;

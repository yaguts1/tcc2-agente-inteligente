/**
 * AgendaPanel Component
 * Painel principal para gerenciar agendas de um paciente
 */

import React, { useState } from "react";
import { useAgenda } from "../../hooks/useAgenda";
import { Agenda, AgendaCreate, AgendaUpdate } from "../../api/agendaApi";
import AgendaForm from "./AgendaForm";
import AgendaList from "./AgendaList";
import "./AgendaPanel.css";

interface AgendaPanelProps {
  pacienteId: string;
}

type ViewMode = "list" | "create" | "edit";

export const AgendaPanel: React.FC<AgendaPanelProps> = ({ pacienteId }) => {
  const agenda = useAgenda(pacienteId);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [editingAgenda, setEditingAgenda] = useState<Agenda | null>(null);

  const handleCreateClick = () => {
    setEditingAgenda(null);
    setViewMode("create");
  };

  const handleEditClick = (agnd: Agenda) => {
    setEditingAgenda(agnd);
    setViewMode("edit");
  };

  const handleFormSubmit = async (data: AgendaCreate | AgendaUpdate) => {
    try {
      if (viewMode === "create") {
        await agenda.createAgenda(data as AgendaCreate);
      } else if (editingAgenda) {
        await agenda.updateAgenda(editingAgenda.id, data as AgendaUpdate);
      }
      setViewMode("list");
      setEditingAgenda(null);
    } catch (error) {
      console.error("Erro ao salvar agenda:", error);
    }
  };

  const handleFormCancel = () => {
    setViewMode("list");
    setEditingAgenda(null);
    agenda.clearError();
  };

  return (
    <div className="agenda-panel">
      <div className="agenda-panel__header">
        <h2 className="agenda-panel__title">Agendas do Paciente</h2>
        <p className="agenda-panel__subtitle">
          Gerencie supressão, redução ou monitoramento de alertas
        </p>
      </div>

      {/* Error Message */}
      {agenda.error && (
        <div className="agenda-panel__alert agenda-panel__alert--error">
          <span>{agenda.error}</span>
          <button
            onClick={agenda.clearError}
            className="agenda-panel__alert-close"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Content */}
      {viewMode === "list" ? (
        <div className="agenda-panel__list-view">
          <button
            className="agenda-panel__create-btn"
            onClick={handleCreateClick}
            disabled={agenda.loading}
          >
            + Criar Nova Agenda
          </button>

          <AgendaList
            agendas={agenda.agendas}
            loading={agenda.loading}
            onEdit={handleEditClick}
            onDelete={agenda.deleteAgenda}
          />
        </div>
      ) : (
        <div className="agenda-panel__form-view">
          <div className="agenda-panel__form-header">
            <h3>
              {viewMode === "create" ? "Criar Nova Agenda" : "Editar Agenda"}
            </h3>
          </div>
          <AgendaForm
            agenda={editingAgenda}
            onSubmit={handleFormSubmit}
            onCancel={handleFormCancel}
            loading={agenda.loading}
          />
        </div>
      )}
    </div>
  );
};

export default AgendaPanel;

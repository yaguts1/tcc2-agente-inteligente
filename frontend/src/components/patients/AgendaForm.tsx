/**
 * AgendaForm Component
 * Formulário para criar/editar agendas
 */

import React, { useState, useEffect } from "react";
import { Agenda, AgendaCreate, AgendaUpdate } from "../../api/agendaApi";
import "./AgendaForm.css";

interface AgendaFormProps {
  agenda?: Agenda | null;
  onSubmit: (data: AgendaCreate | AgendaUpdate) => Promise<void>;
  onCancel?: () => void;
  loading?: boolean;
}

type FormData = AgendaCreate;

const AGENDA_TYPES = [
  { value: "refeicao", label: "Refeição" },
  { value: "cirurgia", label: "Cirurgia" },
  { value: "procedimento", label: "Procedimento" },
  { value: "atendimento", label: "Atendimento" },
  { value: "outro", label: "Outro" },
] as const;

const AGENDA_MODES = [
  { value: "suprimir", label: "Suprimir (ignorar alertas)" },
  { value: "reduzir", label: "Reduzir (diminuir janela)" },
  { value: "monitorar", label: "Monitorar (manter alertas)" },
] as const;

const WEEKDAYS = [
  { value: 0, label: "Seg" },
  { value: 1, label: "Ter" },
  { value: 2, label: "Qua" },
  { value: 3, label: "Qui" },
  { value: 4, label: "Sex" },
  { value: 5, label: "Sab" },
  { value: 6, label: "Dom" },
] as const;

export const AgendaForm: React.FC<AgendaFormProps> = ({
  agenda,
  onSubmit,
  onCancel,
  loading = false,
}) => {
  const [form, setForm] = useState<FormData>({
    tipo: "refeicao",
    modo: "suprimir",
    hora_inicio: "08:00",
    hora_fim: "09:00",
    dias_semana: [1, 2, 3, 4, 5],
    data_inicio: new Date().toISOString().split("T")[0],
    data_fim: null,
    reducao_janela_min: null,
    descricao: "",
  });

  const [isRecurring, setIsRecurring] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize form with existing agenda data
  useEffect(() => {
    if (agenda) {
      setForm({
        tipo: agenda.tipo,
        modo: agenda.modo,
        hora_inicio: agenda.hora_inicio,
        hora_fim: agenda.hora_fim,
        dias_semana: agenda.dias_semana,
        data_inicio: agenda.data_inicio,
        data_fim: agenda.data_fim || null,
        reducao_janela_min: agenda.reducao_janela_min,
        descricao: agenda.descricao,
      });
      setIsRecurring(!!agenda.dias_semana);
    }
  }, [agenda]);

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >
  ) => {
    const { name, value, type } = e.currentTarget;

    if (type === "checkbox") {
      const checked = (e.currentTarget as HTMLInputElement).checked;
      const numberValue = parseInt(name.replace("weekday-", ""));
      setForm((prev) => ({
        ...prev,
        dias_semana: checked
          ? [...(prev.dias_semana || []), numberValue]
          : (prev.dias_semana || []).filter((d) => d !== numberValue),
      }));
    } else if (name === "reducao_janela_min") {
      setForm((prev) => ({
        ...prev,
        [name]: value ? parseInt(value) : null,
      }));
    } else {
      setForm((prev) => ({
        ...prev,
        [name]: value,
      }));
    }
  };

  const validateForm = (): boolean => {
    if (!form.hora_inicio || !form.hora_fim) {
      setError("Horários de início e fim são obrigatórios");
      return false;
    }

    if (form.hora_inicio >= form.hora_fim) {
      setError("Hora de início deve ser antes da hora de fim");
      return false;
    }

    if (form.data_inicio) {
      const inicio = new Date(form.data_inicio);
      if (form.data_fim) {
        const fim = new Date(form.data_fim);
        if (inicio > fim) {
          setError("Data de início deve ser antes da data de fim");
          return false;
        }
      }
    }

    if (isRecurring && (!form.dias_semana || form.dias_semana.length === 0)) {
      setError("Selecione pelo menos um dia da semana");
      return false;
    }

    if (
      form.modo === "reduzir" &&
      (!form.reducao_janela_min || form.reducao_janela_min < 5 || form.reducao_janela_min > 60)
    ) {
      setError("Redução deve estar entre 5 e 60 minutos");
      return false;
    }

    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!validateForm()) {
      return;
    }

    try {
      const submitData = {
        ...form,
        dias_semana: isRecurring ? form.dias_semana : null,
        data_fim: isRecurring ? null : form.data_fim,
      };
      await onSubmit(submitData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao salvar agenda");
    }
  };

  return (
    <form className="agenda-form" onSubmit={handleSubmit}>
      {error && <div className="agenda-form__error">{error}</div>}

      {/* Tipo e Modo */}
      <div className="agenda-form__row">
        <div className="agenda-form__group">
          <label htmlFor="tipo">Tipo de Agenda *</label>
          <select
            id="tipo"
            name="tipo"
            value={form.tipo}
            onChange={handleChange}
            required
          >
            {AGENDA_TYPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="agenda-form__group">
          <label htmlFor="modo">Modo *</label>
          <select
            id="modo"
            name="modo"
            value={form.modo}
            onChange={handleChange}
            required
          >
            {AGENDA_MODES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Horários */}
      <div className="agenda-form__row">
        <div className="agenda-form__group">
          <label htmlFor="hora_inicio">Hora Início *</label>
          <input
            id="hora_inicio"
            type="time"
            name="hora_inicio"
            value={form.hora_inicio}
            onChange={handleChange}
            required
          />
        </div>

        <div className="agenda-form__group">
          <label htmlFor="hora_fim">Hora Fim *</label>
          <input
            id="hora_fim"
            type="time"
            name="hora_fim"
            value={form.hora_fim}
            onChange={handleChange}
            required
          />
        </div>
      </div>

      {/* Tipo de Recorrência */}
      <div className="agenda-form__group">
        <label className="agenda-form__checkbox-label">
          <input
            type="checkbox"
            checked={isRecurring}
            onChange={(e) => setIsRecurring(e.target.checked)}
          />
          Agenda Recorrente (semanal)
        </label>
      </div>

      {/* Dias da Semana (se recorrente) */}
      {isRecurring && (
        <div className="agenda-form__group">
          <label>Dias da Semana *</label>
          <div className="agenda-form__weekdays">
            {WEEKDAYS.map((day) => (
              <label key={day.value} className="agenda-form__day-checkbox">
                <input
                  type="checkbox"
                  name={`weekday-${day.value}`}
                  checked={(form.dias_semana || []).includes(day.value)}
                  onChange={handleChange}
                />
                {day.label}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Data Início */}
      <div className="agenda-form__row">
        <div className="agenda-form__group">
          <label htmlFor="data_inicio">Data Início *</label>
          <input
            id="data_inicio"
            type="date"
            name="data_inicio"
            value={form.data_inicio}
            onChange={handleChange}
            required
          />
        </div>

        {/* Data Fim (se não recorrente) */}
        {!isRecurring && (
          <div className="agenda-form__group">
            <label htmlFor="data_fim">Data Fim</label>
            <input
              id="data_fim"
              type="date"
              name="data_fim"
              value={form.data_fim || ""}
              onChange={handleChange}
            />
          </div>
        )}
      </div>

      {/* Redução Janela (se modo reduzir) */}
      {form.modo === "reduzir" && (
        <div className="agenda-form__group">
          <label htmlFor="reducao_janela_min">Redução de Janela (min) *</label>
          <input
            id="reducao_janela_min"
            type="number"
            name="reducao_janela_min"
            min="5"
            max="60"
            value={form.reducao_janela_min || ""}
            onChange={handleChange}
            placeholder="5-60 minutos"
            required
          />
        </div>
      )}

      {/* Descrição */}
      <div className="agenda-form__group">
        <label htmlFor="descricao">Descrição</label>
        <textarea
          id="descricao"
          name="descricao"
          value={form.descricao || ""}
          onChange={handleChange}
          placeholder="Notas sobre esta agenda..."
          rows={3}
        />
      </div>

      {/* Botões */}
      <div className="agenda-form__buttons">
        <button
          type="submit"
          className="agenda-form__submit"
          disabled={loading}
        >
          {loading ? "Salvando..." : agenda ? "Atualizar" : "Criar"}
        </button>
        {onCancel && (
          <button
            type="button"
            className="agenda-form__cancel"
            onClick={onCancel}
            disabled={loading}
          >
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
};

export default AgendaForm;

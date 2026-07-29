/**
 * API Service for Monitor de Alertas de Reposicionamento
 * All endpoints use relative paths with credentials: "same-origin"
 */

import { getStoredToken, storeToken, storeUser, clearAuth } from './storage';

export interface ApiError {
  message: string;
  status: number;
  details?: any;
}

export class ApiException extends Error {
  status: number;
  details?: any;

  constructor(message: string, status: number, details?: any) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = `Erro ${response.status}`;
    let errorDetails;

    try {
      const errorData = await response.json();
      // fastapi often returns { detail: { code: 'x', message: '...' } }
      if (errorData) {
        if (typeof errorData.message === 'string') {
          errorMessage = errorData.message;
        } else if (typeof errorData.error === 'string') {
          errorMessage = errorData.error;
        } else if (errorData.detail) {
          const det = errorData.detail;
          if (typeof det === 'string') {
            errorMessage = det;
          } else if (det && typeof det.message === 'string') {
            errorMessage = det.message;
          } else if (det && typeof det.code === 'string') {
            errorMessage = det.code;
          }
        }
      }
      errorDetails = errorData;
    } catch {
      errorMessage = response.statusText || errorMessage;
    }

    throw new ApiException(errorMessage, response.status, errorDetails);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

type RequestOptions = RequestInit & {
  responseType?: 'json' | 'blob';
  /** Recebe os cabeçalhos da resposta antes do corpo ser lido. */
  onHeaders?: (headers: Headers) => void;
};

async function request<T>(
  url: string,
  options: RequestOptions = {}
): Promise<T> {
  // DEBUG: log requests to help diagnose why calls to /api/* might not reach backend
  try {
    // avoid logging bodies for security, but show method and url
    // eslint-disable-next-line no-console
    console.debug('[api] request', url, options && options.method ? options.method : 'GET');
  } catch (_) {}

  // Add stored token to Authorization header if available
  const token = getStoredToken();
  const headers = new Headers({
    'Content-Type': 'application/json',
  });

  // Copy existing headers from options
  if (options.headers) {
    if (options.headers instanceof Headers) {
      options.headers.forEach((value, key) => {
        headers.set(key, value);
      });
    } else if (Array.isArray(options.headers)) {
      options.headers.forEach(([key, value]) => {
        headers.set(key, value);
      });
    } else {
      Object.entries(options.headers).forEach(([key, value]) => {
        headers.set(key, String(value));
      });
    }
  }

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  let finalUrl = url;
  // Adjust URL for base path if needed
  if (url.startsWith('/api')) {
    const baseUrl = import.meta.env.BASE_URL;
    if (baseUrl && baseUrl !== '/') {
      finalUrl = `${baseUrl}${url.substring(1)}`;
    }
  }

  const { responseType, onHeaders, ...fetchOptions } = options;

  const response = await fetch(finalUrl, {
    // rely on same-origin behavior and Vite proxy in dev; use same-origin
    // to ensure cookies are handled by the dev server host.
    credentials: 'same-origin',
    headers,
    ...fetchOptions,
  });

  onHeaders?.(response.headers);

  if (responseType === 'blob') {
    if (!response.ok) {
      throw new ApiException(response.statusText || 'Erro no download', response.status);
    }
    return response.blob() as unknown as T;
  }

  return handleResponse<T>(response);
}

/**
 * Como `request`, mas devolve também os cabeçalhos da resposta.
 *
 * Existe para metadados de paginação (`X-Total-Count`): o corpo continua sendo
 * o array puro — que é o contrato de `/frontend/alerts` — e o total, que a
 * lista sozinha não consegue expressar, viaja no cabeçalho.
 */
async function requestComHeaders<T>(
  url: string,
  options: RequestOptions = {}
): Promise<{ dados: T; headers: Headers }> {
  let headers = new Headers();
  const dados = await request<T>(url, {
    ...options,
    onHeaders: (h) => {
      headers = h;
    },
  });
  return { dados, headers };
}

// Auth API
export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
}

export interface AuthResponse {
  username: string;
  display_name?: string | null;
  role?: string;
}

export const authApi = {
  login: async (data: LoginRequest) => {
    const response = await request<AuthResponse & { token?: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    // Store token and user info if provided
    if (response.token) {
      storeToken(response.token);
    }
    storeUser({
      username: response.username,
      display_name: response.display_name,
      role: response.role,
    });
    return response;
  },

  register: async (data: RegisterRequest) => {
    const response = await request<AuthResponse & { token?: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    // Store token and user info if provided
    if (response.token) {
      storeToken(response.token);
    }
    storeUser({
      username: response.username,
      display_name: response.display_name,
      role: response.role,
    });
    return response;
  },

  me: () => request<AuthResponse>('/api/auth/me'),

  logout: async () => {
    try {
      await request<void>('/api/auth/logout', {
        method: 'POST',
      });
    } finally {
      // Always clear local storage even if logout request fails
      clearAuth();
    }
  },
};

// Alert API
/**
 * Por que o alerta foi fechado.
 *
 * Concluir não recebia justificativa: o diálogo era sim/não. Então
 * "reposicionei", "estava em cirurgia", "o paciente recusou", "contraindicado"
 * e "falso alarme, o sensor deslocou" viravam a MESMA linha — e cada um é um
 * fato clínico diferente, que pede ação diferente.
 *
 * `falso_alarme` é o que justifica a lista existir: sem separá-lo, a taxa de
 * falso-positivo é incognoscível, logo inmelhorável. Fadiga de alarme é a razão
 * dominante pela qual sistemas de alerta clínico são abandonados.
 *
 * Ausente vale como `reposicionado` — o caso comum não pede escolha.
 */
export type MotivoFechamento =
  | 'reposicionado'
  | 'em_procedimento'
  | 'recusa_do_paciente'
  | 'contraindicado'
  | 'falso_alarme'
  | 'superficie_especial'
  | 'outro';

/** Rótulo e ajuda de cada motivo, na ordem em que a tela oferece. */
export const MOTIVOS_DE_FECHAMENTO: ReadonlyArray<{
  valor: MotivoFechamento;
  rotulo: string;
  ajuda?: string;
}> = [
  { valor: 'reposicionado', rotulo: 'Reposicionado' },
  { valor: 'em_procedimento', rotulo: 'Em procedimento', ajuda: 'Cirurgia, exame, banho' },
  { valor: 'recusa_do_paciente', rotulo: 'Recusa do paciente' },
  { valor: 'contraindicado', rotulo: 'Contraindicado', ajuda: 'Retalho, fixador, instabilidade' },
  { valor: 'superficie_especial', rotulo: 'Superfície de redistribuição' },
  { valor: 'falso_alarme', rotulo: 'Falso alarme', ajuda: 'Sensor deslocado ou leitura errada' },
  { valor: 'outro', rotulo: 'Outro' },
];

/** Rótulos legíveis de sítio anatômico, para a tabela de alertas. */
export const ROTULO_DE_SITIO: Record<string, string> = {
  sacro: 'Sacro',
  coccige: 'Cóccix',
  trocanter_direito: 'Trocânter D',
  trocanter_esquerdo: 'Trocânter E',
  isquio_direito: 'Ísquio D',
  isquio_esquerdo: 'Ísquio E',
  calcaneo_direito: 'Calcâneo D',
  calcaneo_esquerdo: 'Calcâneo E',
  maleolo_direito: 'Maléolo D',
  maleolo_esquerdo: 'Maléolo E',
  occipital: 'Occipital',
  escapula_direita: 'Escápula D',
  escapula_esquerda: 'Escápula E',
  cotovelo_direito: 'Cotovelo D',
  cotovelo_esquerdo: 'Cotovelo E',
  orelha_direita: 'Orelha D',
  orelha_esquerda: 'Orelha E',
  nariz: 'Nariz',
};

/**
 * Rótulo do sítio, ou `null` quando não há.
 *
 * Sítios sintéticos (`postura:<algo>`, criados quando o firmware envia um rótulo
 * que o mapa do servidor não conhece) não são exibidos: dizem o nome da postura,
 * não uma região do corpo, e mostrá-los como se fossem anatomia confundiria
 * quem lê.
 */
export function rotuloDeSitio(site: string | null): string | null {
  if (!site || site.startsWith('postura:')) return null;
  return ROTULO_DE_SITIO[site] ?? site.replace(/_/g, ' ');
}

export interface Alert {
  id: string;
  /**
   * Paciente do alerta, explícito.
   *
   * A tela obtinha isto desmontando `id` com `split('__')[0]`, o que
   * reimplementava o formato do identificador no cliente. O backend passou a
   * mandá-lo pronto — o formato do `id` volta a ser assunto só do servidor.
   */
  patientId: string;
  patientName: string;
  /**
   * Aqui são `string` (possivelmente vazia), diferente de `Patient`, onde são
   * anuláveis. O caminho do alerta passa por `dividir_cama`, que devolve `''`
   * para paciente sem leito; o de paciente devolve `null`. A âncora em
   * `contrato.ts` é o que garante que essa diferença continue verdadeira.
   */
  room: string;
  bed: string;
  lastRepositioning: string;
  nextRepositioning: string;
  riskLevel: 'high' | 'medium' | 'low';
  status: 'pending' | 'acknowledged' | 'completed';
  /**
   * Por qual caminho o alerta foi fechado. `null` em alertas ainda abertos e
   * nos anteriores a migrations/0007, quando a origem não era registrada.
   *
   * Sem isto, a visão FILTRADA do dashboard recalcula as estatísticas em memória
   * e voltaria a somar adesão da equipe com paciente que se mexeu sozinho.
   */
  closureOrigin: 'equipe' | 'sensor' | 'sistema' | null;
  /** Usuário que fechou, quando foi a equipe. */
  closedBy: string | null;
  /**
   * Sítio anatômico que estourou a janela.
   *
   * "Vire o paciente" é menos útil que "o trocanter direito está sob carga há
   * 60 min": a segunda informação diz PARA QUAL LADO virar. `null` em alertas
   * abertos antes do modelo de carga por sítio.
   */
  site: string | null;
}

export interface AlertsResponse {
  alerts: Alert[];
}

/**
 * Resultado de uma ação em lote sobre alertas.
 *
 * `processed` e `failed` são o que torna a falha PARCIAL visível: o lote pode
 * ter sucesso para a maioria e falhar para alguns (tipicamente 409
 * `transicao_invalida`, quando outra pessoa já agiu sobre aquele alerta).
 * `errors[].alert_id` identifica exatamente quais precisam de nova tentativa.
 */
export interface BatchResult {
  ok: boolean;
  processed: number;
  failed: number;
  /**
   * `alert_id` é opcional: há dois caminhos que alimentam esta lista. O normal
   * reporta qual alerta falhou; o outro é quando a própria task levanta, e ali
   * só existe a exceção — o alerta nem chegou a ser identificado. Estava
   * declarado obrigatório, então a tela exibiria `undefined` no lugar do
   * identificador justamente no caso mais confuso para quem está olhando.
   */
  errors: Array<{ alert_id?: string | null; error: string }>;
}

/**
 * Teto de alertas pedidos numa carga do dashboard.
 *
 * O dashboard filtra em MEMÓRIA (FilterBar), então o que não vier na resposta
 * não existe para o filtro. Com o default do backend (100) uma enfermaria
 * movimentada esconderia alertas sem nenhum sinal na tela. 500 cobre com folga
 * uma unidade real; se ainda assim estourar, `truncado` acende o aviso em vez
 * de a lista mentir por omissão.
 */
const TETO_DE_ALERTAS = 500;

export interface PaginaDeAlertas {
  itens: Alert[];
  /** Quantos casam com os filtros no servidor, antes do corte por `limit`. */
  total: number;
  /** `true` quando o servidor tinha mais do que coube na resposta. */
  truncado: boolean;
}

export const alertsApi = {
  getAlerts: async (horas?: number): Promise<PaginaDeAlertas> => {
    const params = new URLSearchParams({ limit: String(TETO_DE_ALERTAS) });
    if (horas) params.set('horas', String(horas));

    const { dados, headers } = await requestComHeaders<Alert[]>(
      `/api/frontend/alerts?${params.toString()}`
    );
    // Sem o header (versão antiga do backend) assume-se o tamanho da lista:
    // não inventa truncamento que não se pode comprovar.
    const total = Number(headers.get('X-Total-Count') ?? dados.length);
    return {
      itens: dados,
      total: Number.isFinite(total) ? total : dados.length,
      truncado: Number.isFinite(total) && total > dados.length,
    };
  },

  acknowledge: (id: string) =>
    request<void>(`/api/frontend/alerts/${encodeURIComponent(id)}/acknowledge`, {
      method: 'POST',
    }),

  complete: (id: string, motivo?: MotivoFechamento) =>
    request<void>(`/api/frontend/alerts/${encodeURIComponent(id)}/complete`, {
      method: 'POST',
      body: JSON.stringify({ motivo: motivo ?? null }),
    }),

  batchAcknowledge: (alertIds: string[]) =>
    request<BatchResult>('/api/frontend/alerts/batch/acknowledge', {
      method: 'POST',
      body: JSON.stringify({ alert_ids: alertIds }),
    }),

  batchComplete: (alertIds: string[], motivo?: MotivoFechamento) =>
    request<BatchResult>('/api/frontend/alerts/batch/complete', {
      method: 'POST',
      body: JSON.stringify({ alert_ids: alertIds, motivo: motivo ?? null }),
    }),
};

// Timeline API
export interface TimelineEvent {
  id: number;
  paciente_id: string;
  paciente_name: string | null;
  ts: string;
  ts_ms: number;
  tipo: string;
  descricao: string | null;
}

export interface TimelineFilters {
  paciente_id?: string;
  tipo?: string;
  start_ms?: number;
  end_ms?: number;
  limit?: number;
}

export const timelineApi = {
  getEvents: (filters?: TimelineFilters) => {
    const params = new URLSearchParams();
    if (filters?.paciente_id) params.append('paciente_id', filters.paciente_id);
    if (filters?.tipo) params.append('tipo', filters.tipo);
    if (filters?.start_ms) params.append('start_ms', filters.start_ms.toString());
    if (filters?.end_ms) params.append('end_ms', filters.end_ms.toString());
    if (filters?.limit) params.append('limit', filters.limit.toString());
    
    const queryString = params.toString();
    return request<TimelineEvent[]>(`/api/timeline${queryString ? `?${queryString}` : ''}`);
  },
};

// Patients API
export interface Patient {
  id: string;
  name: string;
  /**
   * Quarto e leito são OPCIONAIS.
   *
   * Estavam declarados como `string` obrigatório enquanto o backend devolve
   * `null` para paciente sem leito — e depois da alta esse é o estado normal.
   * O `strict` do TypeScript estava mentindo: `patient.room` chegava
   * `undefined` num campo tipado como `string`, e o erro só apareceria em
   * runtime, num `.toLowerCase()` qualquer.
   */
  room: string | null;
  bed: string | null;
  riskLevel: 'high' | 'medium' | 'low';
  repositioningInterval: number;
  createdAt: string;
  updatedAt: string;
  /**
   * Unidade (ala) em que o paciente está internado.
   *
   * Com mais de uma ala, "Leito 12" sozinho é ambíguo — existe um em cada.
   * `null` só aparece em fichas anteriores à migração de unidades.
   */
  unitId: number | null;
}

export interface CreatePatientRequest {
  name: string;
  room: string;
  bed: string;
  riskLevel: 'high' | 'medium' | 'low';
  /**
   * Opcional e ignorado pelo backend: o intervalo é derivado do perfil de
   * risco. Era obrigatório aqui, o formulário deixava editá-lo e o valor era
   * descartado sem aviso — quem alterasse acreditaria ter mudado o protocolo
   * do paciente. Use `patientsApi.getPerfisRisco()` para exibir o valor real.
   */
  repositioningInterval?: number;
  /**
   * Ala em que o paciente está sendo admitido. Ausente = unidade padrão, para
   * a instalação de uma ala só continuar funcionando sem mudança.
   *
   * Só vale na ADMISSÃO. Mudar de ala é transferência, não edição de
   * formulário: a transferência reinicia o motor de alertas, porque ser
   * erguido para a maca é alívio de pressão real.
   */
  unitId?: number | null;
}

// Units API
export interface Unit {
  id: number;
  nome: string;
  descricao: string | null;
  ativo: number;
}

export const unitsApi = {
  /**
   * Unidades que o usuário logado enxerga. Admin recebe todas.
   *
   * Ler não é privilégio — a enfermeira precisa da lista para escolher onde
   * admitir. Criar e vincular exigem admin.
   */
  list: () => request<Unit[]>('/api/unidades'),

  create: (nome: string, descricao?: string) =>
    request<Unit>('/api/unidades', {
      method: 'POST',
      body: JSON.stringify({ nome, descricao: descricao || null }),
    }),

  getUserUnits: (username: string) =>
    request<{ username: string; unidades: number[] }>(
      `/api/usuarios/${encodeURIComponent(username)}/unidades`,
    ),

  setUserUnits: (username: string, unidades: number[]) =>
    request<{ ok: boolean; username: string; unidades: number[] }>(
      `/api/usuarios/${encodeURIComponent(username)}/unidades`,
      { method: 'PUT', body: JSON.stringify({ unidades }) },
    ),
};

// Escala de Braden — o instrumento que a enfermagem já usa
//
// O risco era um enum de três valores num dropdown, sem escore e sem
// reavaliação, e as janelas de reposicionamento eram variáveis de ambiente
// globais. Numa ala brasileira, Braden É o que vai para o prontuário: uma
// ferramenta que não o consome pede uma SEGUNDA classificação de risco,
// paralela à que a enfermeira já é obrigada a registrar.
export interface BradenSubescores {
  percepcao_sensorial: number;
  umidade: number;
  atividade: number;
  mobilidade: number;
  nutricao: number;
  /** 1 a 3, não 1 a 4 — é assim na escala. */
  friccao_cisalhamento: number;
}

export interface BradenAvaliacao extends BradenSubescores {
  id: number;
  paciente_id: string;
  total: number;
  /** Faixa original de Braden, cinco níveis. */
  faixa: string;
  /** Perfil deste sistema (três níveis), derivado da faixa. */
  perfil: string;
  avaliada_ts: string;
  avaliada_por: string | null;
  observacoes: string | null;
}

export interface BradenEscala {
  subescalas: Record<string, { minimo: number; maximo: number }>;
  total_minimo: number;
  total_maximo: number;
  perfil_por_faixa: Record<string, string>;
  reavaliacao_horas: number;
}

export interface BradenPendentes {
  limite_horas: number;
  internados: number;
  nunca_avaliado: Array<{ paciente_id: string; nome: string | null; cama_id: string | null }>;
  vencidos: Array<{
    paciente_id: string;
    nome: string | null;
    cama_id: string | null;
    ultimo_total: number | null;
    horas_desde_ultima?: number;
  }>;
  pendentes: number;
}

export const bradenApi = {
  /** A escala vem do SERVIDOR, com o mapeamento faixa→perfil junto. */
  escala: () => request<BradenEscala>('/api/braden/escala'),

  pendentes: () => request<BradenPendentes>('/api/braden/pendentes'),

  doPaciente: (pacienteId: string) =>
    request<BradenAvaliacao[]>(`/api/pacientes/${encodeURIComponent(pacienteId)}/braden`),

  registrar: (
    pacienteId: string,
    dados: BradenSubescores & { observacoes?: string | null },
  ) =>
    request<BradenAvaliacao>(`/api/pacientes/${encodeURIComponent(pacienteId)}/braden`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),
};

// Lesões por pressão — a variável de DESFECHO
//
// O sistema media adesão ao reposicionamento e nunca registrava se a lesão
// aconteceu. Sem isto, a correlação que o projeto existe para demonstrar
// (adesão ao protocolo vs. incidência de LPP) não é computável nem em
// princípio: media-se o processo e ignorava-se o resultado.
export interface LesaoAvaliacao {
  ts: string;
  estagio: string;
  comprimento_cm: number | null;
  largura_cm: number | null;
  avaliada_por: string | null;
  observacoes: string | null;
}

export interface Lesao {
  id: number;
  paciente_id: string;
  internacao_id: number | null;
  unidade_id: number | null;
  sitio: string;
  /**
   * `presente_na_admissao` | `adquirida`.
   *
   * Separa prevalência de incidência: lesão que o paciente trouxe não é falha
   * do cuidado desta unidade. Somar as duas pune quem recebe paciente grave de
   * outro serviço — e é esse número que faz uma equipe deixar de registrar.
   */
  origem: string;
  identificada_ts: string;
  identificada_por: string | null;
  fechada_ts: string | null;
  desfecho: string | null;
  observacoes: string | null;
  /** Derivado da avaliação mais recente, nunca duplicado numa coluna. */
  estagio_atual: string | null;
  estagio_inicial: string | null;
  avaliacoes: number;
  historico?: LesaoAvaliacao[];
}

export interface VocabularioLesao {
  sitios: string[];
  origens: string[];
  estagios: string[];
  desfechos: string[];
}

export interface IndicadoresLesao {
  janela_horas: number;
  lesoes_adquiridas: number;
  lesoes_presentes_na_admissao: number;
  pacientes_dia: number;
  /**
   * `null` quando não há paciente-dia na janela. Zero seria o melhor resultado
   * possível, e "não há denominador" é outra coisa.
   */
  incidencia_por_1000_pacientes_dia: number | null;
  pacientes_internados: number;
}

export const lesoesApi = {
  /** Vocabulário vem do SERVIDOR: uma cópia no JS é o começo de duas listas divergentes. */
  vocabulario: () => request<VocabularioLesao>('/api/lesoes/vocabulario'),

  indicadores: (horas = 720) =>
    request<IndicadoresLesao>(`/api/lesoes/indicadores?horas=${horas}`),

  doPaciente: (pacienteId: string) =>
    request<Lesao[]>(`/api/pacientes/${encodeURIComponent(pacienteId)}/lesoes`),

  registrar: (
    pacienteId: string,
    dados: {
      sitio: string;
      origem: string;
      estagio: string;
      observacoes?: string | null;
      comprimento_cm?: number | null;
      largura_cm?: number | null;
    },
  ) =>
    request<Lesao>(`/api/pacientes/${encodeURIComponent(pacienteId)}/lesoes`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),

  avaliar: (
    lesaoId: number,
    dados: { estagio: string; comprimento_cm?: number | null; observacoes?: string | null },
  ) =>
    request<Lesao>(`/api/lesoes/${lesaoId}/avaliacoes`, {
      method: 'POST',
      body: JSON.stringify(dados),
    }),

  fechar: (lesaoId: number, desfecho: string) =>
    request<Lesao>(`/api/lesoes/${lesaoId}/fechamento`, {
      method: 'POST',
      body: JSON.stringify({ desfecho }),
    }),
};

// Simulation API
export interface SimulationRequest {
  duracao_horas: number;
  seed?: number;
  perfil: 'baixo' | 'medio' | 'alto';
}

export interface SimulationResult {
  success: boolean;
  /** Eventos brutos gravados. Antes este campo carregava a contagem de
   *  AMOSTRAS da grade, então a tela exibia "N eventos" com outro número. */
  eventos: number;
  /** Amostras da grade de postura gravadas. */
  amostras: number;
  alertas: number;
  duracao: number;
  error?: string;
  message?: string;
}

/** Intervalo de reposicionamento por nivel de risco, em horas. Vem do backend
 *  (mesma configuracao que o motor de alertas usa) para o formulario nao
 *  manter uma copia divergente da tabela. */
export type PerfisRisco = Record<'high' | 'medium' | 'low', number>;

/**
 * Resultado de `DELETE /api/pacientes/{id}`.
 *
 * `removidos` traz quantas linhas saíram de cada tabela. A exclusão é
 * irreversível e leva junto o histórico clínico (alertas, timeline, grade),
 * então quem executa precisa ver o tamanho do que apagou — "removido com
 * sucesso" não distingue apagar uma ficha vazia de apagar meses de histórico.
 */
export interface DeletePatientResult {
  ok: boolean;
  paciente_id: string;
  removidos: Record<string, number>;
}

export interface DischargeResult {
  ok: boolean;
  paciente_id: string;
  alta_ts: string;
  /** Tempo de internação, em horas. */
  permanencia_horas: number;
  /** Leito que ficou livre, ou `null` se o paciente não estava em nenhum. */
  cama_liberada: string | null;
}

export interface TransferResult {
  ok: boolean;
  paciente_id: string;
  cama_anterior: string | null;
  cama_atual: string | null;
  unidade_anterior: number | null;
  unidade_atual: number | null;
  /** `true` quando o paciente mudou de ala, não só de leito. */
  mudou_de_unidade: boolean;
  ts: string;
}

export const patientsApi = {
  getPerfisRisco: () => request<PerfisRisco>('/api/perfis-risco'),

  getPatients: () => request<Patient[]>('/api/pacientes'),

  getPatient: (id: string) => request<Patient>(`/api/pacientes/${id}`),

  createPatient: (data: CreatePatientRequest) =>
    request<Patient>('/api/pacientes', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePatient: (id: string, data: Partial<CreatePatientRequest>) =>
    request<Patient>(`/api/pacientes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  /**
   * Remove o paciente e TODO o rastro clínico dele.
   *
   * NÃO é o caminho para dar alta — para isso existe `discharge`, que preserva
   * o histórico. Este endpoint é para ERRO DE CADASTRO (paciente duplicado,
   * criado no lugar errado), que é coisa diferente e rara, e por isso segue
   * restrito a admin.
   */
  deletePatient: (id: string) =>
    request<DeletePatientResult>(`/api/pacientes/${id}`, {
      method: 'DELETE',
    }),

  /**
   * Encerra a internação PRESERVANDO o histórico clínico.
   *
   * Libera o leito, fecha o período no histórico de leito e desvincula o
   * device — sem isso, a leitura do sensor do leito continuaria caindo no
   * prontuário de quem já foi embora.
   */
  discharge: (id: string, motivo?: string) =>
    request<DischargeResult>(`/api/pacientes/${id}/alta`, {
      method: 'POST',
      body: JSON.stringify({ motivo: motivo || null }),
    }),

  /**
   * Move o paciente de leito como operação própria.
   *
   * A transferência É um reposicionamento: ser erguido para a maca, levado
   * pelo corredor e reacomodado é o maior alívio de pressão do dia. Por isso
   * ela reinicia o motor de alertas — o que editar o campo no formulário não
   * faz, porque um formulário não sabe que houve deslocamento físico.
   */
  transfer: (id: string, room: string, bed: string, unitId?: number | null) =>
    request<TransferResult>(`/api/pacientes/${id}/transferencia`, {
      method: 'POST',
      body: JSON.stringify({ room, bed, unitId: unitId ?? null }),
    }),

  simulateData: (id: string, data: SimulationRequest) =>
    request<SimulationResult>(`/api/pacientes/${id}/simular`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Agenda (supressão de alertas) API
export interface AgendaCreate {
  tipo: 'refeicao' | 'cirurgia' | 'procedimento' | 'atendimento' | 'outro';
  modo: 'suprimir' | 'reduzir' | 'monitorar';
  hora_inicio: string; // HH:MM
  hora_fim: string; // HH:MM
  dias_semana?: number[] | null; // [0-6] ou null (agendamento único)
  data_inicio: string; // YYYY-MM-DD
  data_fim?: string | null; // YYYY-MM-DD ou null
  reducao_janela_min?: number | null; // 5-60
  descricao?: string;
}

export interface AgendaUpdate {
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

export interface Agenda extends AgendaCreate {
  id: number;
  paciente_id: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgendasResponse {
  agendas: Agenda[];
  total: number;
}

export const agendaApi = {
  listAgendas: async (pacienteId: string, ativo?: boolean): Promise<AgendasResponse> => {
    const qs = ativo !== undefined ? `?ativo=${ativo}` : '';
    // O backend retorna um array direto; embrulhamos no formato esperado.
    const agendas = await request<Agenda[]>(`/api/pacientes/${pacienteId}/agenda${qs}`);
    const arr = Array.isArray(agendas) ? agendas : [];
    return { agendas: arr, total: arr.length };
  },

  createAgenda: (pacienteId: string, data: AgendaCreate) =>
    request<Agenda>(`/api/pacientes/${pacienteId}/agenda`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAgenda: (pacienteId: string, agendaId: number, data: AgendaUpdate) =>
    request<Agenda>(`/api/pacientes/${pacienteId}/agenda/${agendaId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteAgenda: (pacienteId: string, agendaId: number) =>
    request<void>(`/api/pacientes/${pacienteId}/agenda/${agendaId}`, {
      method: 'DELETE',
    }),
};

// Device Events API
export interface DeviceEvent {
  id: number;
  device_id: string;
  ts: string;
  ts_ms: number;
  payload: any;
  processed_at: string | null;
  created_at: string;
}

export interface BedStats {
  cama_id: string;
  count: number;
  first_event: string;
  last_event: string;
  current_patient: {
    id: string;
    name: string;
  } | null;
}

export interface DeviceEventsStats {
  /** TODOS os órfãos pendentes, inclusive os que nenhum leito alcança. */
  total_orphans: number;
  /** Os que a reconciliação por leito consegue resolver (soma de `beds`). */
  orfaos_com_leito: number;
  /**
   * Órfãos sem `cama_id` no payload. Nenhum botão desta tela os resolve — eles
   * dependem da reconciliação por dispositivo/tempo. Antes entravam no
   * `total_orphans` sem aparecer em leito nenhum, então o operador reconciliava
   * tudo e o número não zerava, sem explicação.
   */
  orfaos_sem_leito: number;
  /** O agrupamento por leito foi calculado sobre uma amostra cortada. */
  amostra_truncada: boolean;
  beds: BedStats[];
}

export interface ReconcileResponse {
  processed: number;
  skipped: number;
  patient_name?: string;
  cama_id?: string;
  error?: string;
}

export const deviceEventsApi = {
  getEvents: () => request<DeviceEvent[]>('/api/device_events'),

  getStats: () => request<DeviceEventsStats>('/api/device_events/stats'),

  reconcile: () =>
    request<ReconcileResponse>('/api/device_events/reconcile', {
      method: 'POST',
    }),

  reconcileBed: (camaId: string) =>
    request<ReconcileResponse>(`/api/device_events/reconcile_bed/${camaId}`, {
      method: 'POST',
    }),
};

// Dashboard Stats API
export interface DashboardStats {
  activeAlerts: number;
  acknowledgedAlerts: number;
  completedToday: number;
  totalPatients: number;
  /**
   * Alertas que deixaram de estar abertos, POR QUALQUER MOTIVO. Não é adesão:
   * inclui o paciente que se mexeu sozinho. Ver `teamCompletionRate`.
   */
  completionRate: number;
  /** Fechados por alguém da equipe clicando na tela. */
  completedByTeam: number;
  /** Fechados pelo motor ao detectar movimento espontâneo do paciente. */
  completedBySensor: number;
  /**
   * Fechados antes de a origem passar a ser registrada (migrations/0007).
   * Ficam de fora das duas contagens acima de propósito: não dá para saber
   * retroativamente quem fechou, e chutar "equipe" inventaria adesão.
   */
  completedUnknownOrigin: number;
  /**
   * A taxa que responde "a equipe está virando os pacientes?" — só conta
   * fechamentos pela equipe. `completionRate` responde outra pergunta.
   */
  teamCompletionRate: number;
  /**
   * Pacientes com leito atribuído SEM leituras recentes (sensor, rede ou
   * ingestão com problema). Existe porque "nenhum alerta" é ambíguo: pode
   * significar que está tudo bem, ou que o sistema parou de receber dados.
   */
  unmonitoredPatients: number;
  /**
   * Mediana de detecção → alguém viu, em minutos. `null` quando ninguém
   * reconheceu nada: zero seria um número excelente, e "ninguém olhou" é o
   * oposto disso.
   *
   * Mediana e não média — um alerta esquecido a noite inteira levaria a média
   * às alturas e esconderia que o resto da ala responde em minutos.
   */
  medianAckMinutes: number | null;
  /** Quantos alertas entraram no cálculo acima. */
  acknowledgedCount: number;
  /** Minutos sem dados a partir dos quais o paciente conta como não monitorado. */
  monitoringLimitMin: number;
  /**
   * Pacientes com Braden vencido ou nunca avaliado.
   *
   * Fica ao lado de `unmonitoredPatients` porque são as duas formas de o sistema
   * estar cego: um não recebe dados, o outro vigia com uma classificação de
   * risco que pode não valer mais — e a janela de reposicionamento vem dela.
   */
  bradenPendentes: number;
  /** Subconjunto dos pendentes que nunca passou pelo instrumento. */
  bradenNuncaAvaliado: number;
  bradenLimiteHoras: number;
}

export const statsApi = {
  getStats: () => request<DashboardStats>('/api/stats'),
};

/**
 * Situação de monitoramento de um paciente com leito atribuído.
 *
 * `/api/stats` já traz a CONTAGEM de pacientes sem dados, e o dashboard exibe
 * o aviso. O que faltava era o detalhe: quem. Sem ele, o aviso diz "3
 * pacientes sem monitoramento — verifique o sensor" e não há como descobrir
 * quais leitos checar sem ir ao log do servidor.
 */
export interface StatusMonitoramento {
  paciente_id: string;
  nome: string | null;
  cama_id: string | null;
  ultima_leitura: string | null;
  minutos_sem_dados: number | null;
  monitorado: boolean;
  /** Distingue "o sensor parou" de "nunca chegou leitura" (erro de instalação
   *  ou de vínculo device↔leito, cuja ação corretiva é outra). */
  nunca_recebeu_dados: boolean;
}

export interface MonitoramentoResponse {
  limite_min: number;
  total_com_leito: number;
  monitorados: number;
  sem_monitoramento: number;
  pacientes_sem_monitoramento: StatusMonitoramento[];
  pacientes: StatusMonitoramento[];
}

export const monitoramentoApi = {
  getStatus: () => request<MonitoramentoResponse>('/api/monitoramento'),
};

// Export API
export interface ExportParams {
  startDate?: string;
  endDate?: string;
  status?: 'pending' | 'acknowledged' | 'completed';
  patientId?: string;
}

export const formatDateForExport = (dateStr: string): string => {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('pt-BR');
};

export const exportAlertsToCSV = async (params: ExportParams): Promise<void> => {
  const queryParams = new URLSearchParams();
  if (params.startDate) queryParams.append('start_date', params.startDate);
  if (params.endDate) queryParams.append('end_date', params.endDate);
  if (params.status) queryParams.append('status', params.status);
  if (params.patientId) queryParams.append('patient_id', params.patientId);

  const response = await request<Blob>(`/api/alerts/export/csv?${queryParams.toString()}`, {
    headers: {
      'Accept': 'text/csv',
    },
    responseType: 'blob',
  });

  // Create download link
  const url = window.URL.createObjectURL(response);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `alertas_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
};

export const exportAlertsToPDF = async (params: ExportParams): Promise<void> => {
  const queryParams = new URLSearchParams();
  if (params.startDate) queryParams.append('start_date', params.startDate);
  if (params.endDate) queryParams.append('end_date', params.endDate);
  if (params.status) queryParams.append('status', params.status);
  if (params.patientId) queryParams.append('patient_id', params.patientId);

  const response = await request<Blob>(`/api/alerts/export/pdf?${queryParams.toString()}`, {
    headers: {
      'Accept': 'application/pdf',
    },
    responseType: 'blob',
  });

  // Create download link
  const url = window.URL.createObjectURL(response);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `alertas_${new Date().toISOString().split('T')[0]}.pdf`);
  document.body.appendChild(link);
  link.click();
  link.remove();
};

// ---------------------------------------------------------------------------
// Gestão de usuários (admin)
//
// As rotas existiam desde o commit que criou o router e nenhuma tela as
// consumia: não havia como listar, promover, desativar ou resetar senha. Numa
// instalação real isso significa que quem sai da equipe mantém acesso
// indefinidamente.
// ---------------------------------------------------------------------------

/**
 * Tamanho mínimo de senha. Espelha `SENHA_MIN_LEN` do backend
 * (interface/api_shared.py), que é quem de fato recusa.
 *
 * Havia TRÊS respostas diferentes para "qual é a senha mínima": o formulário
 * de cadastro exigia 6, o endpoint de cadastro não exigia nada e os endpoints
 * de troca exigiam 8. Quem cadastrava com 6 passava — e depois era impedido de
 * trocar para uma senha do mesmo tamanho.
 */
export const SENHA_MIN_LEN = 8;

export type PapelUsuario = 'admin' | 'staff';

export interface Usuario {
  username: string;
  display_name: string | null;
  role: PapelUsuario;
  ativo: boolean;
  created_at: string | null;
  /**
   * Registro no conselho e categoria profissional.
   *
   * COFEN Res. 429/2012 exige identificação por nome E registro. Sem eles, o
   * que o sistema produz é apoio de plantão, não documentação.
   */
  coren: string | null;
  categoria: string | null;
}

export const usuariosApi = {
  listar: () => request<Usuario[]>('/api/usuarios'),

  /**
   * Cria uma conta a partir de uma sessão já autenticada.
   *
   * Usa `/auth/register`, que é o mesmo endpoint da tela de cadastro — a
   * diferença é a sessão: com usuários já cadastrados, `_autorizar_cadastro`
   * exige sessão ativa ou token de convite, e responde 403 para anônimos.
   *
   * Sem isto havia um beco sem saída: deslogado a tela de cadastro aparecia mas
   * o servidor recusava; logado, a tela de cadastro não existe em lugar nenhum.
   * Criar o segundo usuário da instalação só era possível por `curl`.
   */
  criar: (username: string, password: string, display_name?: string) =>
    request<{ username: string; role: PapelUsuario }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password, display_name }),
    }),

  alterarPapel: (username: string, role: PapelUsuario) =>
    request<{ ok: boolean; username: string; role: PapelUsuario }>(
      `/api/usuarios/${encodeURIComponent(username)}/papel`,
      { method: 'PATCH', body: JSON.stringify({ role }) }
    ),

  alterarAtivo: (username: string, ativo: boolean) =>
    request<{ ok: boolean; username: string; ativo: boolean }>(
      `/api/usuarios/${encodeURIComponent(username)}/ativo`,
      { method: 'PATCH', body: JSON.stringify({ ativo }) }
    ),

  /** Reset por administrador (esquecimento, comprometimento). Derruba as
   *  sessões do alvo — senão o JWT já emitido seguiria valendo por horas. */
  definirSenha: (username: string, nova_senha: string) =>
    request<{ ok: boolean; username: string }>(
      `/api/usuarios/${encodeURIComponent(username)}/senha`,
      { method: 'POST', body: JSON.stringify({ nova_senha }) }
    ),

  /** Troca da própria senha. Exige a atual e ENCERRA a própria sessão. */
  trocarPropriaSenha: (senha_atual: string, nova_senha: string) =>
    request<{ ok: boolean; sessoes_encerradas: boolean }>('/api/usuarios/eu/senha', {
      method: 'POST',
      body: JSON.stringify({ senha_atual, nova_senha }),
    }),
};

// ---------------------------------------------------------------------------
// Backup (admin)
// ---------------------------------------------------------------------------

export interface BackupItem {
  filename: string;
  size_mb: number;
  created_at: string;
  age_hours: number;
  /** Presentes apenas na verificação. */
  ok?: boolean;
  motivo?: string | null;
  linhas?: Record<string, number> | null;
}

export interface BackupStatus {
  total: number;
  validos: number;
  invalidos: string[];
  ultimo_valido: string | null;
  idade_horas: number | null;
  /**
   * `false` quando o backup mais recente é pequeno demais em relação ao banco
   * vivo — sinal de que é cópia de OUTRO banco. Já aconteceu: a suíte de
   * testes gravava cópias do banco de teste no diretório real e a mais nova,
   * válida e recentíssima, virava o "último backup bom".
   */
  proporcional: boolean;
  /**
   * Recente E proporcional. Responde "estou coberto?" para o backup LOCAL, que
   * cobre erro de operação e corrupção de banco — não perda da VM.
   */
  saudavel: boolean;
  replicacao: EstadoReplicacao;
}

/**
 * A cópia FORA da VM.
 *
 * Backup no mesmo disco do banco não cobre disco morto nem VM apagada. O
 * transporte vive num script do host (`scripts/replicar_backups.sh`), que
 * deixa um recibo — sem ele, uma replicação que parou de rodar seria
 * indistinguível de uma que funciona, que é exatamente a falha que backup
 * existe para evitar.
 */
export interface EstadoReplicacao {
  /** `false` = esta instalação não replica; informar sem alarmar. */
  configurada: boolean;
  intervalo_horas: number | null;
  /** Resultado da última execução do script. */
  ok: boolean | null;
  idade_horas: number | null;
  destino: string | null;
  arquivos: number | null;
  erro: string | null;
  /** Configurada, última execução OK e dentro do intervalo esperado. */
  saudavel: boolean;
}

export const backupApi = {
  criar: () => request<{ ok: boolean; filename: string }>('/api/admin/backup/create', {
    method: 'POST',
  }),

  listar: () => request<{ backups: BackupItem[]; count: number }>('/api/admin/backup/list'),

  status: () => request<BackupStatus>('/api/admin/backup/status'),

  verificar: () =>
    request<{ backups: BackupItem[]; invalidos: number }>('/api/admin/backup/verify', {
      method: 'POST',
    }),

  limpar: (keepDays: number) =>
    request<{ ok: boolean; removed_count: number }>(
      `/api/admin/backup/cleanup?keep_days=${keepDays}`,
      { method: 'POST' }
    ),
};

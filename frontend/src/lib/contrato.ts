/**
 * Amarra os tipos escritos à mão em `api.ts` ao contrato gerado do backend.
 *
 * O problema que isto resolve: `Alert` e `Patient` eram declarações
 * independentes do que o servidor promete, mantidas em sincronia por
 * disciplina. E já tinham divergido — `room`/`bed` eram `string` obrigatório no
 * TypeScript enquanto o backend devolve `null` para paciente sem leito, que
 * depois da alta é o estado normal. O `strict` estava mentindo.
 *
 * Aqui as duas declarações se encontram: se o schema do backend mudar de um
 * jeito que o tipo do frontend não acompanhe, `npm run typecheck` FALHA — em
 * vez de o erro aparecer em runtime, num `.toLowerCase()` de um `undefined`.
 *
 * `api-gerada.d.ts` sai de `npm run gen:api-types`, que lê `openapi/openapi.json`.
 * Não editar à mão.
 */
import type { components } from './api-gerada';
import type {
  Alert,
  BatchResult,
  DashboardStats,
  MonitoramentoResponse,
  Patient,
  Unit,
  Usuario,
} from './api';

type DoBackend = components['schemas'];

/**
 * Falha a compilação se `T` e `U` não forem o mesmo tipo.
 *
 * Bidirecional de propósito: `extends` sozinho aceitaria um tipo mais amplo de
 * um lado, que é justamente como `string` passou a conviver com `string | null`
 * sem ninguém perceber.
 */
type Identico<T, U> = [T] extends [U] ? ([U] extends [T] ? true : never) : never;

// Campos que o backend promete e a tela consome. Se um deles mudar de tipo ou
// de opcionalidade no servidor, a linha correspondente para de compilar.
type AlertDoBackend = Pick<
  DoBackend['FrontendAlert'],
  | 'id'
  | 'patientId'
  | 'patientName'
  | 'room'
  | 'bed'
  | 'riskLevel'
  | 'status'
  // A escada de escalonamento. Ancorada porque é a única informação da tela
  // cujo VALOR é decidido no servidor e cujo significado é clínico: se o
  // conjunto de níveis divergir entre os dois lados, a tela renderiza um nível
  // que não existe e cai no caso default — silenciosamente de volta ao estado
  // anterior, em que o alerta das 03:00 parecia igual ao das 06:55.
  | 'minutesOpen'
  | 'escalationLevel'
>;
type AlertDaTela = Pick<
  Alert,
  | 'id'
  | 'patientId'
  | 'patientName'
  | 'room'
  | 'bed'
  | 'riskLevel'
  | 'status'
  | 'minutesOpen'
  | 'escalationLevel'
>;

type PatientDoBackend = Pick<
  DoBackend['FrontendPatient'],
  'id' | 'name' | 'room' | 'bed' | 'riskLevel'
>;
type PatientDaTela = Pick<Patient, 'id' | 'name' | 'room' | 'bed' | 'riskLevel'>;

// As duas linhas abaixo são o teste. Não têm efeito em runtime.
export const _alertaConfere: Identico<AlertDoBackend, AlertDaTela> = true;
export const _pacienteConfere: Identico<PatientDoBackend, PatientDaTela> = true;

// Demais respostas que a SPA consome. Cada uma foi ligada a um `response_model`
// no backend: sem ele a rota não entra no spec com forma nenhuma, e não há
// contra o que comparar — o tipo daqui volta a ser declaração independente,
// mantida em sincronia por disciplina.
type StatsDoBackend = DoBackend['DashboardStatsResponse'];
type MonitoramentoDoBackend = DoBackend['MonitoramentoResponse'];
type LoteDoBackend = DoBackend['BatchResultResponse'];
type UnidadeDoBackend = DoBackend['UnidadeResponse'];
type UsuarioDoBackend = Pick<
  DoBackend['UsuarioResponse'],
  'username' | 'role' | 'ativo' | 'coren' | 'categoria'
>;
type UsuarioDaTela = Pick<Usuario, 'username' | 'role' | 'ativo' | 'coren' | 'categoria'>;

export const _statsConfere: Identico<StatsDoBackend, DashboardStats> = true;
export const _monitoramentoConfere: Identico<
  MonitoramentoDoBackend,
  MonitoramentoResponse
> = true;
export const _loteConfere: Identico<LoteDoBackend, BatchResult> = true;
export const _unidadeConfere: Identico<UnidadeDoBackend, Unit> = true;
export const _usuarioConfere: Identico<UsuarioDoBackend, UsuarioDaTela> = true;

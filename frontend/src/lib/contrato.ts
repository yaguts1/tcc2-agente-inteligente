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
import type { Alert, Patient } from './api';

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
  'id' | 'patientId' | 'patientName' | 'room' | 'bed' | 'riskLevel' | 'status'
>;
type AlertDaTela = Pick<
  Alert,
  'id' | 'patientId' | 'patientName' | 'room' | 'bed' | 'riskLevel' | 'status'
>;

type PatientDoBackend = Pick<
  DoBackend['FrontendPatient'],
  'id' | 'name' | 'room' | 'bed' | 'riskLevel'
>;
type PatientDaTela = Pick<Patient, 'id' | 'name' | 'room' | 'bed' | 'riskLevel'>;

// As duas linhas abaixo são o teste. Não têm efeito em runtime.
export const _alertaConfere: Identico<AlertDoBackend, AlertDaTela> = true;
export const _pacienteConfere: Identico<PatientDoBackend, PatientDaTela> = true;

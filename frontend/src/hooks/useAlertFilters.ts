/**
 * Tipo dos filtros de alerta usados pelo Dashboard e pela FilterBar.
 *
 * O hook `useAlertFilters` e o `useAlertFilterPresets` que viviam aqui foram
 * removidos: nada os chamava (o DashboardPage importava o modulo mas
 * reimplementava o estado com useState) e o codigo ainda lia
 * `process.env.NODE_ENV`, que e `undefined` num bundle Vite e teria quebrado
 * se algum dia fosse executado.
 */

export interface AlertFilters {
  severities?: string[];
  patientId?: string;
  alertTypes?: string[];
  /**
   * ATENCAO: 'CRITICAL' nunca casa com nada. `Alert.riskLevel` (lib/api.ts) so
   * assume 'high' | 'medium' | 'low', mas a FilterBar oferece a opcao
   * "Critica" — selecionar sempre devolve zero linhas. Mantido aqui para nao
   * mudar a UI numa limpeza; precisa ser resolvido decidindo se a opcao sai da
   * FilterBar ou se o backend passa a classificar risco critico.
   */
  severity?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  /** Espelha `Alert.status`. Era 'open', que nenhum alerta jamais tem. */
  status?: 'pending' | 'acknowledged' | 'completed';
  searchText?: string;
  dateFrom?: Date;
  dateTo?: Date;
}

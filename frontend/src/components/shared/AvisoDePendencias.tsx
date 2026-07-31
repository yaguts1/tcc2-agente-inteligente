/**
 * Diz que há ações esperando a rede.
 *
 * Uma fila que reenvia em silêncio resolve METADE do problema — a ação não se
 * perde — e deixa a outra metade intacta: a pessoa não sabe se o que ela fez
 * chegou, e na dúvida ou refaz, ou anota no papel. As duas saídas são piores
 * que o defeito original, porque produzem registro duplicado ou registro
 * paralelo ao sistema.
 *
 * Fica no layout e não numa página, porque a rede cai enquanto se anda: a
 * pessoa pode estar em Pacientes quando a fila esvazia.
 */
import { CloudOff } from 'lucide-react';
import { useAlerts } from '../../contexts/AlertsContext';

export function AvisoDePendencias() {
  const { acoesPendentes } = useAlerts();
  if (acoesPendentes.length === 0) return null;

  const total = acoesPendentes.length;

  return (
    <div
      // `role="status"` e não `alert`: é informação de estado, não urgência.
      // `alert` interromperia o leitor de tela no meio de outra leitura, e a
      // pendência não é mais importante que o alerta clínico que ela pode estar
      // narrando.
      role="status"
      className="flex items-center gap-2 rounded-md border border-amber-500/50 bg-amber-100 px-3 py-2 text-sm text-amber-900 dark:bg-amber-900 dark:text-amber-100"
    >
      <CloudOff className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
      <span>
        {total === 1
          ? '1 ação aguardando conexão'
          : `${total} ações aguardando conexão`}
        {' — '}
        {/* O que a pessoa precisa saber é que NÃO precisa refazer. */}
        serão enviadas automaticamente.
      </span>
    </div>
  );
}

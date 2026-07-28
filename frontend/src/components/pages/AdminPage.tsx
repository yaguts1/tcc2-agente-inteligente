import { useState } from 'react';
import { Settings, Bed, Users, Database, Building2 } from 'lucide-react';
import { OrphanEventsPanel } from '../admin/OrphanEventsPanel';
import { UsersPanel } from '../admin/UsersPanel';
import { BackupPanel } from '../admin/BackupPanel';
import { UnitsPanel } from '../admin/UnitsPanel';

/**
 * Página de administração.
 *
 * Era exclusivamente a reconciliação de eventos órfãos, enquanto dez rotas de
 * gestão de usuários e de backup existiam sem nenhuma tela que as consumisse:
 * trocar papel, desativar uma conta de quem saiu da equipe, redefinir senha e
 * conferir se o backup realmente restaura só eram possíveis por `curl`.
 *
 * As abas são botões com ARIA em vez de um componente de terceiros: o projeto
 * não tem `@radix-ui/react-tabs` instalado e três painéis não justificam uma
 * dependência nova.
 */
const ABAS = [
  { id: 'orfaos', rotulo: 'Eventos órfãos', icone: Bed },
  { id: 'usuarios', rotulo: 'Usuários', icone: Users },
  { id: 'unidades', rotulo: 'Unidades', icone: Building2 },
  { id: 'backup', rotulo: 'Backup', icone: Database },
] as const;

type AbaId = (typeof ABAS)[number]['id'];

export function AdminPage() {
  const [aba, setAba] = useState<AbaId>('orfaos');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-foreground flex items-center gap-2">
          <Settings className="w-6 h-6" />
          Administração
        </h1>
        <p className="text-muted-foreground mt-1">
          Reconciliação de eventos, contas de acesso, unidades e backup do banco
        </p>
      </div>

      <div role="tablist" aria-label="Seções de administração" className="flex flex-wrap gap-1 border-b">
        {ABAS.map(({ id, rotulo, icone: Icone }) => {
          const ativa = aba === id;
          return (
            <button
              key={id}
              role="tab"
              id={`aba-${id}`}
              aria-selected={ativa}
              aria-controls={`painel-${id}`}
              onClick={() => setAba(id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-2 text-sm transition-colors ${
                ativa
                  ? 'border-primary font-medium text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              <Icone className="w-4 h-4" />
              {rotulo}
            </button>
          );
        })}
      </div>

      {/*
        Cada painel é montado só quando sua aba está ativa. Não é economia de
        render: os três buscam dados no `useEffect` de montagem, e manter os
        ocultos vivos faria a página disparar as requisições de todos eles a
        cada visita — inclusive `/api/usuarios`, que expõe as contas.
      */}
      <div role="tabpanel" id={`painel-${aba}`} aria-labelledby={`aba-${aba}`}>
        {aba === 'orfaos' && <OrphanEventsPanel />}
        {aba === 'usuarios' && <UsersPanel />}
        {aba === 'unidades' && <UnitsPanel />}
        {aba === 'backup' && <BackupPanel />}
      </div>
    </div>
  );
}

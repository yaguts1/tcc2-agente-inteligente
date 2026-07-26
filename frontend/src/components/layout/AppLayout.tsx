import { ReactNode, useState } from 'react';
import {
  Bell,
  Users,
  LayoutDashboard,
  History,
  Settings,
  KeyRound,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { Button } from '../ui/button';
import { CriticalAlertBadge } from '../alerts/CriticalAlertBadge';
import { CriticalAlert } from '../../hooks/useCriticalAlerts';
import { NavLink } from 'react-router-dom';
import { cn } from '../ui/utils';
import { getStoredUser } from '../../lib/storage';
import { TrocarSenhaDialog } from '../common/TrocarSenhaDialog';

interface AppLayoutProps {
  children: ReactNode;
  currentUser: string;
  onLogout: () => void;
  criticalAlerts?: {
    total: number;
    highRisk: number;
    acknowledgedMedium: number;
    hasNew: boolean;
    alerts: CriticalAlert[];
  };
  onCriticalAlertClick?: (alert: CriticalAlert) => void;
}

// `to` é o caminho real na URL. A navegação usa <Link>, e não botões com
// onClick: assim o item vira um link de verdade — abre em nova aba, responde
// ao botão do meio, aparece no histórico e pode ser copiado e enviado a um
// colega. O estado "ativo" passa a vir da URL, e não de um useState paralelo
// que podia divergir do que está na tela.
const navigation = [
  { to: '/', name: 'Dashboard', icon: LayoutDashboard },
  { to: '/historico', name: 'Histórico', icon: History },
  { to: '/pacientes', name: 'Pacientes', icon: Users },
  // `somenteAdmin`: a página de Admin passou a ser quase toda de operações
  // restritas (contas e backup exigem o papel `admin` no backend). Oferecê-la
  // a todos significaria um item de menu que abre uma tela de erros 403.
  // É afordância, não autorização — quem decide é o backend, pelo JWT.
  { to: '/admin', name: 'Admin', icon: Settings, somenteAdmin: true },
] as const;

export function AppLayout({
  children,
  currentUser,
  onLogout,
  criticalAlerts,
  onCriticalAlertClick,
}: AppLayoutProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [trocandoSenha, setTrocandoSenha] = useState(false);

  const ehAdmin = getStoredUser()?.role === 'admin';
  const itensVisiveis = navigation.filter((item) => !('somenteAdmin' in item) || ehAdmin);

  return (
    <div className="min-h-screen bg-bg">
      {/* Mobile Header */}
      <div className="lg:hidden bg-surface border-b border-border sticky top-0 z-40">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="bg-primary/10 p-2 rounded-lg">
              <Bell className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h1 className="text-text">Alertas</h1>
            </div>
          </div>
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="p-2 hover:bg-muted rounded-lg"
            aria-label="Menu"
          >
            {isMobileMenuOpen ? (
              <X className="w-6 h-6" />
            ) : (
              <Menu className="w-6 h-6" />
            )}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMobileMenuOpen && (
          <div className="border-t border-border bg-surface">
            <nav className="p-4 space-y-2">
              {itensVisiveis.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={() => setIsMobileMenuOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors',
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'hover:bg-muted text-foreground'
                      )
                    }
                  >
                    {/* NavLink já aplica aria-current="page" no item ativo,
                        então leitores de tela anunciam a página atual — antes
                        a única indicação era a cor, inacessível por si só. */}
                    <Icon className="w-5 h-5" aria-hidden="true" />
                    <span>{item.name}</span>
                  </NavLink>
                );
              })}
            </nav>
            <div className="border-t border-border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-foreground">{currentUser}</p>
                  <p className="text-muted-foreground">Conectado</p>
                </div>
                <Button variant="outline" size="sm" onClick={onLogout}>
                  <LogOut className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Desktop Sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col bg-surface border-r border-border">
        <div className="flex flex-col flex-1 min-h-0">
          <div className="flex items-center gap-3 px-6 py-5 border-b border-border">
            <div className="bg-primary/10 p-2 rounded-lg">
              <Bell className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-text">Alertas</h1>
              <p className="text-muted-foreground">Reposicionamento</p>
            </div>
          </div>

          <nav className="flex-1 px-4 py-4 space-y-1">
            {itensVisiveis.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-foreground'
                    )
                  }
                >
                  <Icon className="w-5 h-5" aria-hidden="true" />
                  <span>{item.name}</span>
                </NavLink>
              );
            })}
          </nav>

          <div className="border-t border-border p-4">
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-foreground">{currentUser}</p>
                <p className="text-muted-foreground">Conectado</p>
              </div>
              {criticalAlerts && criticalAlerts.total > 0 && (
                <CriticalAlertBadge
                  totalCritical={criticalAlerts.total}
                  highRisk={criticalAlerts.highRisk}
                  acknowledgedMedium={criticalAlerts.acknowledgedMedium}
                  hasNewCritical={criticalAlerts.hasNew}
                  criticalAlerts={criticalAlerts.alerts}
                  onAlertClick={onCriticalAlertClick}
                />
              )}
            </div>
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={() => setTrocandoSenha(true)}
            >
              <KeyRound className="w-4 h-4 mr-2" />
              Trocar senha
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start"
              onClick={onLogout}
            >
              <LogOut className="w-4 h-4 mr-2" />
              Sair
            </Button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:pl-64">
        <div className="px-4 py-6 lg:px-8">{children}</div>
      </main>

      {/* Trocar a própria senha encerra a sessão no servidor, então o diálogo
          desconecta ao concluir — senão o usuário seguiria clicando e
          recebendo 401 sem entender o motivo. */}
      <TrocarSenhaDialog
        aberto={trocandoSenha}
        onOpenChange={setTrocandoSenha}
        onSessaoEncerrada={onLogout}
      />
    </div>
  );
}

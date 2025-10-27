import { ReactNode, useState } from 'react';
import {
  Bell,
  Users,
  LayoutDashboard,
  History,
  Settings,
  LogOut,
  Menu,
  X,
} from 'lucide-react';
import { Button } from '../ui/button';
import { CriticalAlertBadge } from '../alerts/CriticalAlertBadge';
import { CriticalAlert } from '../../hooks/useCriticalAlerts';
import { cn } from '../ui/utils';

interface AppLayoutProps {
  children: ReactNode;
  currentUser: string;
  onLogout: () => void;
  currentPage: 'dashboard' | 'timeline' | 'patients' | 'admin';
  onNavigate: (page: 'dashboard' | 'timeline' | 'patients' | 'admin') => void;
  criticalAlerts?: {
    total: number;
    highRisk: number;
    acknowledgedMedium: number;
    hasNew: boolean;
    alerts: CriticalAlert[];
  };
  onCriticalAlertClick?: (alert: CriticalAlert) => void;
}

const navigation = [
  { id: 'dashboard', name: 'Dashboard', icon: LayoutDashboard },
  { id: 'timeline', name: 'Histórico', icon: History },
  { id: 'patients', name: 'Pacientes', icon: Users },
  { id: 'admin', name: 'Admin', icon: Settings },
] as const;

export function AppLayout({
  children,
  currentUser,
  onLogout,
  currentPage,
  onNavigate,
  criticalAlerts,
  onCriticalAlertClick,
}: AppLayoutProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

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
              {navigation.map((item) => {
                const Icon = item.icon;
                const isActive = currentPage === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      onNavigate(item.id as any);
                      setIsMobileMenuOpen(false);
                    }}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted text-foreground'
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    <span>{item.name}</span>
                  </button>
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
            {navigation.map((item) => {
              const Icon = item.icon;
              const isActive = currentPage === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id as any)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors',
                    isActive
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted text-foreground'
                  )}
                >
                  <Icon className="w-5 h-5" />
                  <span>{item.name}</span>
                </button>
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
    </div>
  );
}

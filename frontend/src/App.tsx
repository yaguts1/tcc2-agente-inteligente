import { Suspense, lazy, useState } from 'react';
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { AuthLayout } from './components/auth/AuthLayout';
import { LoginForm } from './components/auth/LoginForm';
import { RegisterForm } from './components/auth/RegisterForm';
import { AppLayout } from './components/layout/AppLayout';
import { FullPageSpinner } from './components/shared/Spinner';
import { SessionExpirationAlert } from './components/common/SessionExpirationAlert';
import { Toaster } from './components/ui/sonner';
import { ErrorBoundary } from './components/ErrorBoundary';
import { WebSocketProvider } from './contexts/WebSocketContext';
import { AlertsProvider } from './contexts/AlertsContext';
import { NotFoundPage } from './components/pages/NotFoundPage';

// Carregamento sob demanda: antes tudo ia num único chunk de ~434 kB, então
// quem abria a tela de login já baixava o Admin, o editor de agendas e o painel
// de exportação. Com o `switch` sobre useState isso era impossível de dividir —
// só o roteamento por URL cria a fronteira para o code splitting.
const DashboardPage = lazy(() =>
  import('./components/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })),
);
const TimelinePage = lazy(() =>
  import('./components/pages/TimelinePage').then((m) => ({ default: m.TimelinePage })),
);
const PatientsPage = lazy(() =>
  import('./components/pages/PatientsPage').then((m) => ({ default: m.PatientsPage })),
);
const AdminPage = lazy(() =>
  import('./components/pages/AdminPage').then((m) => ({ default: m.AdminPage })),
);

/**
 * `basename` vem do Vite (`--base=/TCC/` no build). Sem isso o router montaria
 * as rotas na raiz do domínio e a navegação quebraria assim que a aplicação
 * fosse servida sob um prefixo — que é justamente como ela roda em produção.
 */
const BASENAME = import.meta.env.BASE_URL?.replace(/\/$/, '') || '/';

function AreaAutenticada({ usuario, onLogout }: { usuario: string; onLogout: () => void }) {
  return (
    <WebSocketProvider isAuthenticated>
      <AlertsProvider>
        <AppLayout currentUser={usuario} onLogout={onLogout}>
          {/* Suspense por rota: a troca de página mostra o spinner enquanto o
              chunk daquela tela chega, em vez de travar a interface. */}
          <Suspense fallback={<FullPageSpinner />}>
            <Outlet />
          </Suspense>
        </AppLayout>
      </AlertsProvider>
    </WebSocketProvider>
  );
}

export default function App() {
  const { user, isLoading, error, login, register, logout, isAuthenticated } = useAuth();
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');

  const handleLogin = async (username: string, password: string) => {
    await login(username, password);
  };

  const handleRegister = async (username: string, password: string, displayName: string) => {
    const success = await register(username, password, displayName);
    if (success) {
      setAuthMode('login');
    }
  };

  if (isLoading) {
    return <FullPageSpinner />;
  }

  if (!isAuthenticated) {
    return (
      <ErrorBoundary>
        <AuthLayout
          title={authMode === 'login' ? 'Sistema de Alertas de Reposicionamento' : 'Criar Conta'}
          description={
            authMode === 'login'
              ? 'Gestão de pacientes com risco de úlcera de pressão'
              : 'Cadastre-se para acessar o sistema'
          }
        >
          {authMode === 'login' ? (
            <LoginForm
              onSubmit={handleLogin}
              onSwitchToRegister={() => setAuthMode('register')}
              isLoading={isLoading}
              error={error}
            />
          ) : (
            <RegisterForm
              onSubmit={handleRegister}
              onSwitchToLogin={() => setAuthMode('login')}
              isLoading={isLoading}
              error={error}
            />
          )}
        </AuthLayout>
        <Toaster />
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <BrowserRouter basename={BASENAME}>
        <Routes>
          <Route element={<AreaAutenticada usuario={user?.username || 'Usuário'} onLogout={logout} />}>
            <Route index element={<DashboardPage />} />
            <Route path="historico" element={<TimelinePage />} />
            <Route path="pacientes" element={<PatientsPage />} />
            <Route path="admin" element={<AdminPage />} />
            {/* URL desconhecida mostra uma página de erro em vez de uma tela
                em branco — antes o `switch` caía no `default` e exibia o
                Dashboard, escondendo o erro de digitação ou o link quebrado. */}
            <Route path="*" element={<NotFoundPage />} />
          </Route>
          {/* Compatibilidade: /dashboard passa a redirecionar para a raiz. */}
          <Route path="/dashboard" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <SessionExpirationAlert showWarning={true} />
      <Toaster />
    </ErrorBoundary>
  );
}

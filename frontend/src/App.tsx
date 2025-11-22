import { useState } from 'react';
import { useAuth } from './hooks/useAuth';
import { AuthLayout } from './components/auth/AuthLayout';
import { LoginForm } from './components/auth/LoginForm';
import { RegisterForm } from './components/auth/RegisterForm';
import { AppLayout } from './components/layout/AppLayout';
import { DashboardPage } from './components/pages/DashboardPage';
import { TimelinePage } from './components/pages/TimelinePage';
import { PatientsPage } from './components/pages/PatientsPage';
import { AdminPage } from './components/pages/AdminPage';
import { FullPageSpinner } from './components/shared/Spinner';
import { SessionExpirationAlert } from './components/common/SessionExpirationAlert';
import { Toaster } from './components/ui/sonner';
import { ErrorBoundary } from './components/ErrorBoundary';
import { WebSocketProvider } from './contexts/WebSocketContext';

type Page = 'dashboard' | 'timeline' | 'patients' | 'admin';

export default function App() {
  const { user, isLoading, error, login, register, logout, isAuthenticated } = useAuth();
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');

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

  const renderPage = () => {
    switch (currentPage) {
      case 'dashboard':
        return <DashboardPage />;
      case 'timeline':
        return <TimelinePage />;
      case 'patients':
        return <PatientsPage />;
      case 'admin':
        return <AdminPage />;
      default:
        return <DashboardPage />;
    }
  };

  return (
    <ErrorBoundary>
      <WebSocketProvider isAuthenticated={isAuthenticated}>
        <AppLayout
          currentUser={user?.username || 'Usuário'}
          onLogout={logout}
          currentPage={currentPage}
          onNavigate={setCurrentPage}
        >
          {renderPage()}
        </AppLayout>
      </WebSocketProvider>
      <SessionExpirationAlert showWarning={true} />
      <Toaster />
    </ErrorBoundary>
  );
}

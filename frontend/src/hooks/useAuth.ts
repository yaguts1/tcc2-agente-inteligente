import { useEffect, useState } from 'react';
import { authApi, ApiException } from '../lib/api';

export function useAuth() {
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const data = await authApi.me();
      setUser(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException && err.status === 401) {
        setUser(null);
      } else {
        setError('Erro ao verificar autenticação');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (username: string, password: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await authApi.login({ username, password });
      setUser(data);
      return true;
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.status === 401) {
          setError('Usuário ou senha inválidos');
        } else if (err.status === 400) {
          setError('Dados inválidos');
        } else {
          setError('Erro ao fazer login');
        }
      } else {
        setError('Erro de conexão');
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (username: string, password: string, displayName?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await authApi.register({
        username,
        password,
        display_name: displayName,
      });
      setUser(data);
      return true;
    } catch (err) {
      if (err instanceof ApiException) {
        if (err.status === 400) {
          setError('Dados inválidos ou usuário já existe');
        } else {
          setError('Erro ao criar conta');
        }
      } else {
        setError('Erro de conexão');
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
      setUser(null);
    } catch (err) {
      console.error('Erro ao fazer logout:', err);
    }
  };

  return {
    user,
    isLoading,
    error,
    login,
    register,
    logout,
    isAuthenticated: !!user,
  };
}

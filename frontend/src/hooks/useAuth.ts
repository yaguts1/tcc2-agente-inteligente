import { useEffect, useState } from 'react';
import { authApi, ApiException } from '../lib/api';
import { getStoredUser, getStoredToken, getSessionTimeRemaining } from '../lib/storage';

export function useAuth() {
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      // First, try to use stored user and token
      const storedUser = getStoredUser();
      const storedToken = getStoredToken();

      if (storedUser && storedToken) {
        // Check session validity by calling /me endpoint
        try {
          const data = await authApi.me();
          setUser(data);
          setError(null);
          return;
        } catch (err) {
          // If /me fails with 401, stored token is invalid
          if (err instanceof ApiException && err.status === 401) {
            setUser(null);
            setError(null);
          } else {
            setError('Erro ao verificar autenticação');
          }
          return;
        }
      }

      // If no stored user/token, set user to null
      setUser(null);
      setError(null);
    } catch (err) {
      setError('Erro ao verificar autenticação');
      console.error('[useAuth] checkAuth error:', err);
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
      setUser(null);
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
      setUser(null);
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } catch (err) {
      console.error('[useAuth] Erro ao fazer logout:', err);
    } finally {
      setUser(null);
    }
  };

  const getSessionInfo = () => ({
    timeRemaining: getSessionTimeRemaining(),
    isValid: !!getStoredToken(),
  });

  return {
    user,
    isLoading,
    error,
    login,
    register,
    logout,
    isAuthenticated: !!user,
    getSessionInfo,
  };
}

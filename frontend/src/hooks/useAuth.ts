import { useEffect, useState } from 'react';
import { authApi, ApiException } from '../lib/api';
import { getStoredUser, getStoredToken, getSessionTimeRemaining, storeUser, storeToken, clearAuth } from '../lib/storage';

export function useAuth() {
  const [user, setUser] = useState<{ username: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      // Try to validate session with backend (uses cookie from server or Authorization header)
      // The backend sets httpOnly cookie which is auto-sent with requests
      try {
        const data = await authApi.me();
        setUser(data);
        
        // Also restore localStorage from backend response for consistency
        const storedUser = getStoredUser();
        const storedToken = getStoredToken();
        
        // If we have user data but no stored token, generate one
        // (happens when returning to site and /me validates via cookie)
        if (data.username && !storedToken) {
          const fallbackToken = `${data.username}:${Math.floor(Date.now() / 1000)}`;
          storeToken(fallbackToken);
        }
        
        // Update user info if missing
        if (!storedUser) {
          storeUser({
            username: data.username,
            display_name: data.display_name,
            role: data.role,
          });
        }
        setError(null);
        setIsLoading(false);
      } catch (err) {
        // If /me fails, session is invalid or expired
        if (err instanceof ApiException && err.status === 401) {
          clearAuth();
          setUser(null);
          setError(null);
        } else {
          // Other errors (network, etc) - don't force logout
          // User will be treated as unauthenticated but localStorage stays for retry
          setUser(null);
          setError(null);
        }
        setIsLoading(false);
      }
    } catch (err) {
      setError('Erro ao verificar autenticação');
      console.error('[useAuth] checkAuth error:', err);
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

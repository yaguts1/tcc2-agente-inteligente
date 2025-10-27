// Thin compatibility wrapper expected by legacy UI components.
// Most app code imports from './api' (login/register/me/logout).
// Delegate to the canonical `lib/api.ts` implementation which
// already handles credentials and error mapping.

import { authApi } from './lib/api';

export async function login(username: string, password: string) {
  return authApi.login({ username, password });
}

export async function register(username: string, password: string, displayName?: string) {
  return authApi.register({ username, password, display_name: displayName });
}

export async function me() {
  return authApi.me();
}

export async function logout() {
  return authApi.logout();
}

export default {
  login,
  register,
  me,
  logout,
};

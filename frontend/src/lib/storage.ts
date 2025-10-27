/**
 * Storage utilities for persistent authentication
 * Handles localStorage operations with error boundaries
 */

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';
const SESSION_EXPIRY_KEY = 'auth_session_expiry';

/**
 * Get stored authentication token
 * Falls back to cookie-based session if token not available
 */
export function getStoredToken(): string | null {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return null;

    // Check if session has expired
    const expiry = localStorage.getItem(SESSION_EXPIRY_KEY);
    if (expiry && new Date(expiry) < new Date()) {
      // Session expired, clear everything
      clearAuth();
      return null;
    }

    return token;
  } catch (err) {
    console.error('[storage] Error reading token:', err);
    return null;
  }
}

/**
 * Store authentication token and session info
 * @param token Auth token/session ID
 * @param expiryHours How many hours until token expires (default: 8)
 */
export function storeToken(token: string, expiryHours: number = 8): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);

    // Set expiry time
    const expiry = new Date();
    expiry.setHours(expiry.getHours() + expiryHours);
    localStorage.setItem(SESSION_EXPIRY_KEY, expiry.toISOString());
  } catch (err) {
    console.error('[storage] Error storing token:', err);
  }
}

/**
 * Get stored user information
 */
export function getStoredUser(): { username: string; display_name?: string | null; role?: string } | null {
  try {
    const userJson = localStorage.getItem(USER_KEY);
    if (!userJson) return null;
    return JSON.parse(userJson);
  } catch (err) {
    console.error('[storage] Error reading user:', err);
    return null;
  }
}

/**
 * Store user information
 */
export function storeUser(user: { username: string; display_name?: string | null; role?: string }): void {
  try {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch (err) {
    console.error('[storage] Error storing user:', err);
  }
}

/**
 * Check if session is still valid
 */
export function isSessionValid(): boolean {
  try {
    const expiry = localStorage.getItem(SESSION_EXPIRY_KEY);
    if (!expiry) return false;
    return new Date(expiry) > new Date();
  } catch (err) {
    console.error('[storage] Error checking session validity:', err);
    return false;
  }
}

/**
 * Get remaining session time in milliseconds
 */
export function getSessionTimeRemaining(): number {
  try {
    const expiry = localStorage.getItem(SESSION_EXPIRY_KEY);
    if (!expiry) return 0;

    const expiryTime = new Date(expiry).getTime();
    const now = new Date().getTime();
    return Math.max(0, expiryTime - now);
  } catch (err) {
    console.error('[storage] Error calculating session time:', err);
    return 0;
  }
}

/**
 * Clear all authentication data
 */
export function clearAuth(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(SESSION_EXPIRY_KEY);
  } catch (err) {
    console.error('[storage] Error clearing auth:', err);
  }
}

/**
 * Get all stored auth data (for debugging)
 */
export function getAuthDebugInfo(): {
  token: string | null;
  user: any | null;
  expiry: string | null;
  isValid: boolean;
  timeRemaining: number;
} {
  return {
    token: getStoredToken(),
    user: getStoredUser(),
    expiry: localStorage.getItem(SESSION_EXPIRY_KEY),
    isValid: isSessionValid(),
    timeRemaining: getSessionTimeRemaining(),
  };
}

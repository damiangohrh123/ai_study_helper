// api.js
// Utility functions for making API requests (e.g., fetchWithAuth) with JWT and token refresh logic.
// Does not manage state or context—just network helpers for use throughout the app.

const BASE_URL = process.env.REACT_APP_API_URL;

/**
 * Fetch with automatic token refresh for protected endpoints.
 * @param {string} url
 * @param {object} options
 * @param {function} setJwt - Optional, only needed if you want to update JWT in state.
 * @returns {Promise<Response>}
 */
export async function fetchWithAuth(url, options = {}, setJwt, logout) {
  try {
    // Get jwt token from localStorage
    const token = localStorage.getItem('ai_study_helper_jwt');

    // Add Authorization header if token exists
    options.headers = {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    // Make the fetch request
    let res = await fetch(url, options);

    // If 401 (Unauthorized), try refresh once
    if (res.status === 401) {
      const refreshRes = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });

      // Refresh failed → logout
      if (!refreshRes.ok) {
        logout?.();
        throw new SessionExpiredError();
      }

      const { access_token } = await refreshRes.json();

      // No token returned → logout
      if (!access_token) {
        logout?.();
        throw new SessionExpiredError();
      }

      // Save new token
      localStorage.setItem('ai_study_helper_jwt', access_token);
      setJwt?.(access_token);

      // Retry original request with new token
      options.headers = {
        ...options.headers,
        Authorization: `Bearer ${access_token}`,
      };

      res = await fetch(url, options);

      // Still unauthorized → force logout
      if (res.status === 401) {
        logout?.();
        throw new SessionExpiredError();
      }
    }

    // Handle other non-OK responses
    if (!res.ok) {
      const errorData = await res.json().catch(() => null);
      throw new Error(errorData?.detail || errorData?.error || 'API request failed');
    }

    return res;
  } catch (err) {
    // Network or other error
    throw err instanceof Error ? err : new Error('Network error');
  }
}

// PATCH rename chat session
// Throws SessionExpiredError if session expired (UI should handle)
export async function renameChatSession(sessionId, title, setJwt, logout) {
  const res = await fetchWithAuth(
    `${BASE_URL}/chat/sessions/${sessionId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    },
    setJwt,
    logout
  );
  return res;
}

// DELETE chat session
// Throws SessionExpiredError if session expired (UI should handle)
export async function deleteChatSession(sessionId, setJwt, logout) {
  const res = await fetchWithAuth(
    `${BASE_URL}/chat/sessions/${sessionId}`,
    { method: 'DELETE' },
    setJwt,
    logout
  );
  return res;
}

// Fetch user progress (subjects and concepts)
// Throws SessionExpiredError if session expired (UI should handle)
export async function fetchProgress(setJwt, logout) {
  const res = await fetchWithAuth(
    `${BASE_URL}/progress`,
    {},
    setJwt,
    logout
  );
  return res.json();
}

// Fetch recent reflection signals
// Throws SessionExpiredError if session expired (UI should handle)
export async function fetchReflection(setJwt, logout, days = 7) {
  const res = await fetchWithAuth(
    `${BASE_URL}/progress/reflection?days=${days}`,
    {},
    setJwt,
    logout
  );
  return res.json();
}

// Custom error for session expiration
export class SessionExpiredError extends Error {
  constructor(message = 'Session expired. Please log in again.') {
    super(message);
    this.name = 'SessionExpiredError';
  }
}
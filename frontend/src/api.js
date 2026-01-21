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
export async function fetchWithAuth(url, options = {}, setJwt) {
  try {
    const token = localStorage.getItem('ai_study_helper_jwt');
    options.headers = { ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) };

    let res = await fetch(url, options);

    // If 401, try refresh once
    if (res.status === 401) {
      const refreshRes = await fetch(`${BASE_URL}/auth/refresh`, { method: 'POST', credentials: 'include' });
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        if (data.access_token) {
          localStorage.setItem('ai_study_helper_jwt', data.access_token);
          if (setJwt) setJwt(data.access_token);
          options.headers = { ...options.headers, Authorization: `Bearer ${data.access_token}` };
          res = await fetch(url, options);
          // If still 401 after refresh, force logout (optional: throw)
          if (res.status === 401) {
            throw new Error('Session expired. Please log in again.');
          }
        }
      } else {
        throw new Error('Session expired. Please log in again.');
      }
    }

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
export async function renameChatSession(sessionId, title, setJwt) {
  const res = await fetchWithAuth(
    `${BASE_URL}/chat/sessions/${sessionId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    },
    setJwt
  );
  return res;
}

// DELETE chat session
export async function deleteChatSession(sessionId, setJwt) {
  const res = await fetchWithAuth(
    `${BASE_URL}/chat/sessions/${sessionId}`,
    { method: 'DELETE' },
    setJwt
  );
  return res;
}

// Fetch user progress (subjects and concepts)
export async function fetchProgress(setJwt) {
  const res = await fetchWithAuth(
    `${BASE_URL}/progress`,
    {},
    setJwt
  );
  return res.json();
}

// Fetch recent reflection signals
export async function fetchReflection(setJwt, days = 7) {
  const res = await fetchWithAuth(
    `${BASE_URL}/progress/reflection?days=${days}`,
    {},
    setJwt
  );
  return res.json();
}
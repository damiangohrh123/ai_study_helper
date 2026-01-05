// api.js
// Utility functions for making API requests (e.g., fetchWithAuth) with JWT and token refresh logic.
// Does not manage state or context—just network helpers for use throughout the app.
/**
 * Fetch with automatic token refresh for protected endpoints.
 * @param {string} url
 * @param {object} options
 * @param {function} setJwt - Optional, only needed if you want to update JWT in state.
 * @returns {Promise<Response>}
 */
export async function fetchWithAuth(url, options = {}, setJwt) {
  const token = localStorage.getItem('ai_study_helper_jwt');
  options.headers = options.headers || {};
  if (token) options.headers['Authorization'] = `Bearer ${token}`;

  let res = await fetch(url, options);

  if (res.status === 401) {
    const refreshRes = await fetch('http://localhost:8000/auth/refresh', { method: 'POST', credentials: 'include' });
    if (refreshRes.ok) {
      const data = await refreshRes.json();
      if (data.access_token) {
        localStorage.setItem('ai_study_helper_jwt', data.access_token);
        if (setJwt) setJwt(data.access_token);
        options.headers['Authorization'] = `Bearer ${data.access_token}`;
        res = await fetch(url, options);
      }
    }
  }
  return res;
}
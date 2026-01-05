// Login.js
// Handles Google login and sets JWT on success.
import { GoogleLogin } from '@react-oauth/google';

function Login({ setJwt }) {
  const handleSuccess = async (res) => {
    try {
      // Google returns a credential (ID token)
      const idToken = res?.credential;
      if (!idToken) throw new Error('No token received');

      // Send the Google token to the backend to exchange for the JWT
      const response = await fetch('http://localhost:8000/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: idToken }),
      });

      // Parse backend JSON response
      const data = await response.json();

      // If backend gives an access token, save & update app auth state
      if (data?.access_token) {
        localStorage.setItem('ai_study_helper_jwt', data.access_token);
        setJwt(data.access_token);
      } else {
        throw new Error(data?.detail || data?.msg || 'Login failed');
      }
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <div className="App login-container">
      <h2>AI Study Helper Login</h2>
      <div className="login-google">
        <GoogleLogin onSuccess={handleSuccess} onError={() => alert('Google login failed')} />
      </div>
      <p className="login-note">
        Only registered users can use the app. Please sign in with Google to continue.
      </p>
    </div>
  );
}

export default Login;
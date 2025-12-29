
import React, { useState } from 'react';
import './App.css';
import { GoogleLogin } from '@react-oauth/google';

function App() {
  const [jwt, setJwt] = useState(() => localStorage.getItem('ai_study_helper_jwt') || null);
  const [showLogin, setShowLogin] = useState(!jwt);
  // Generate a persistent session_id for this user (per browser tab)
  const getSessionId = () => {
    let id = window.localStorage.getItem('ai_study_helper_session_id');
    if (!id) {
      id = 'sess-' + Math.random().toString(36).slice(2) + Date.now();
      window.localStorage.setItem('ai_study_helper_session_id', id);
    }
    return id;
  };
  const sessionId = getSessionId();
  const [messages, setMessages] = useState([
    { sender: 'ai', text: 'Hello! How can I help you study today?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [image, setImage] = useState(null);
  const [imageUploading, setImageUploading] = useState(false);
  const handleImageChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setImage(e.target.files[0]);
    }
  };


  // Unified send handler for both text and image
  const handleSend = async () => {
    if (!input.trim() && !image) return;
    let userMsg = null;
    if (input.trim() && image) {
      userMsg = { sender: 'user', text: input + ' [Image attached: ' + image.name + ']' };
    } else if (input.trim()) {
      userMsg = { sender: 'user', text: input };
    } else if (image) {
      userMsg = { sender: 'user', text: '[Image attached: ' + image.name + ']' };
    }
    if (userMsg) setMessages(msgs => [...msgs, userMsg]);
    setLoading(true);
    setImageUploading(true);
    setInput('');
    try {
      const formData = new FormData();
      if (input.trim()) formData.append('message', input);
      if (image) formData.append('file', image);
      formData.append('session_id', sessionId);
      const res = await fetch('http://localhost:8000/ask', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (data.response) {
        setMessages(msgs => [...msgs, { sender: 'ai', text: data.response }]);
      } else {
        setMessages(msgs => [...msgs, { sender: 'ai', text: data.error || 'Error: No response from server.' }]);
      }
    } catch (err) {
      setMessages(msgs => [...msgs, { sender: 'ai', text: 'Error: Could not reach server.' }]);
    }
    setImage(null);
    setLoading(false);
    setImageUploading(false);
  };



  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSend();
  };

  if (showLogin) {
    return (
      <div className="App" style={{ maxWidth: 400, margin: '40px auto', padding: 20 }}>
        <h2>AI Study Helper Login</h2>
        <div style={{ margin: '32px 0' }}>
          <GoogleLogin
            onSuccess={async credentialResponse => {
              const idToken = credentialResponse.credential;
              const res = await fetch('http://localhost:8000/google-login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: idToken })
              });
              const data = await res.json();
              if (data.access_token) {
                localStorage.setItem('ai_study_helper_jwt', data.access_token);
                setJwt(data.access_token);
                setShowLogin(false);
              } else {
                alert('Google login failed: ' + (data.detail || data.msg || 'Unknown error'));
              }
            }}
            onError={() => {
              alert('Google login failed');
            }}
          />
        </div>
      </div>
    );
  }

  // Chat UI (shown after login)
  return (
    <div className="App" style={{ maxWidth: 500, margin: '40px auto', padding: 20 }}>
      <h2>AI Study Helper</h2>
      <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 16, minHeight: 200, background: '#fafafa', marginBottom: 16 }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{ textAlign: msg.sender === 'user' ? 'right' : 'left', margin: '8px 0' }}>
            <span style={{ fontWeight: msg.sender === 'user' ? 'bold' : 'normal' }}>
              {msg.sender === 'user' ? 'You' : 'AI'}:
            </span> {msg.text}
          </div>
        ))}
        {loading && <div style={{ color: '#888' }}>AI is typing...</div>}
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your question..."
          style={{ flex: 1, padding: 8, borderRadius: 4, border: '1px solid #ccc' }}
          disabled={loading}
        />
        <input
          type="file"
          accept="image/*"
          onChange={handleImageChange}
          disabled={imageUploading}
        />
        {image && <span style={{ fontSize: 12 }}>{image.name}</span>}
        <button onClick={handleSend} disabled={loading || imageUploading || (!input.trim() && !image)} style={{ padding: '8px 16px' }}>
          {loading || imageUploading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  );
}

export default App;

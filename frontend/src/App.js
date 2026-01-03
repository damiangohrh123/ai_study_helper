import React, { useState } from 'react';
import './App.css';
import { GoogleLogin } from '@react-oauth/google';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

function App() {
  const [jwt, setJwt] = useState(() => localStorage.getItem('ai_study_helper_jwt') || null);
  const [showLogin, setShowLogin] = useState(!jwt);
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [image, setImage] = useState(null);
  const [imageUploading, setImageUploading] = useState(false);

  // Helper to fetch with auto-refresh
  async function fetchWithAuth(url, options, setJwt) {
    let jwt = localStorage.getItem('ai_study_helper_jwt');
    options = options || {};
    options.headers = options.headers || {};
    if (jwt) options.headers['Authorization'] = `Bearer ${jwt}`;
    let res = await fetch(url, options);
    if (res.status === 401) {
      // Try to refresh token
      const refreshRes = await fetch('http://localhost:8000/auth/refresh', { method: 'POST', credentials: 'include' });
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        if (data.access_token) {
          localStorage.setItem('ai_study_helper_jwt', data.access_token);
          setJwt(data.access_token);
          // Retry original request with new token
          options.headers['Authorization'] = `Bearer ${data.access_token}`;
          res = await fetch(url, options);
        }
      }
    }
    return res;
  }

  // Fetch chat sessions after login
  React.useEffect(() => {
    if (!showLogin && jwt) {
      fetchWithAuth('http://localhost:8000/chat/sessions', {}, setJwt)
        .then(res => res.json())
        .then(data => {
          setSessions(data);
          if (data.length > 0) {
            setSelectedSession(data[0].id);
          }
        });
    }
  }, [showLogin, jwt]);

  // Fetch chat history for selected session
  React.useEffect(() => {
    if (!showLogin && jwt && selectedSession) {
      fetchWithAuth(`http://localhost:8000/chat/history?session_id=${selectedSession}`, {}, setJwt)
        .then(res => res.json())
        .then(data => {
          if (Array.isArray(data) && data.length > 0) {
            setMessages(data);
          } else {
            setMessages([{ sender: 'ai', text: 'Hello! How can I help you study today?' }]);
          }
        })
        .catch(() => {
          setMessages([{ sender: 'ai', text: 'Hello! How can I help you study today?' }]);
        });
    }
  }, [showLogin, jwt, selectedSession]);
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
      if (selectedSession) formData.append('session_id', selectedSession);
      const headers = jwt ? { 'Authorization': `Bearer ${jwt}` } : {};
      const res = await fetchWithAuth('http://localhost:8000/chat/ask', {
        method: 'POST',
        body: formData,
        headers
      }, setJwt);
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
              const res = await fetch('http://localhost:8000/auth/google', {
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
  const handleLogout = () => {
    localStorage.clear();
    setJwt(null);
    setShowLogin(true);
    setMessages([]);
  };
  return (
    <div className="App" style={{ display: 'flex', maxWidth: 900, margin: '40px auto', padding: 20 }}>
      {/* Sidebar for chat sessions */}
      <div style={{ width: 220, marginRight: 24, borderRight: '1px solid #eee', paddingRight: 16 }}>
        <h3 style={{ marginTop: 0 }}>Chats</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {sessions.map(session => (
            <li key={session.id} style={{ marginBottom: 8 }}>
              <button
                style={{
                  width: '100%',
                  textAlign: 'left',
                  background: selectedSession === session.id ? '#e6f7e6' : '#fff',
                  border: '1px solid #ccc',
                  borderRadius: 6,
                  padding: '8px 10px',
                  cursor: 'pointer',
                  fontWeight: selectedSession === session.id ? 'bold' : 'normal'
                }}
                onClick={() => setSelectedSession(session.id)}
              >
                {session.title || 'New Chat'}
              </button>
            </li>
          ))}
        </ul>
        <button
          style={{ width: '100%', marginTop: 12, padding: '8px 0', borderRadius: 6, background: '#f4f6fb', border: '1px solid #ccc' }}
          onClick={async () => {
            const title = prompt('Enter a title for the new chat:') || 'New Chat';
            const res = await fetch('http://localhost:8000/chat/sessions', {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${jwt}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ title })
            });
            const data = await res.json();
            if (data && data.id) {
              setSessions(s => [data, ...s]);
              setSelectedSession(data.id);
            }
          }}
        >+ New Chat</button>
      </div>
      {/* Main chat area */}
      <div style={{ flex: 1 }}>
        <h2>AI Study Helper</h2>
        <button onClick={handleLogout} style={{ float: 'right', marginBottom: 8 }}>Logout</button>
        <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 16, minHeight: 200, background: '#fafafa', marginBottom: 16 }}>
          {messages.map((msg, idx) => (
            <div
              key={idx}
              style={{
                textAlign: msg.sender === 'user' ? 'right' : 'left',
                margin: '8px 0',
                background: msg.sender === 'ai' ? '#f4f6fb' : '#e6f7e6',
                borderRadius: 8,
                padding: 12,
                maxWidth: '90%',
                marginLeft: msg.sender === 'ai' ? 0 : 'auto',
                marginRight: msg.sender === 'user' ? 0 : 'auto',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
              }}
            >
              <span style={{ fontWeight: msg.sender === 'user' ? 'bold' : 'normal', color: '#555' }}>
                {msg.sender === 'user' ? 'You' : 'AI'}:
              </span>{' '}
              {msg.sender === 'ai' ? (
                <ReactMarkdown
                  remarkPlugins={[remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                >
                  {msg.text}
                </ReactMarkdown>
              ) : (
                <span>{msg.text}</span>
              )}
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
    </div>
  );
}

export default App;

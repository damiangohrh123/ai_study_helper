import React, { useState, useEffect } from 'react';
import './App.css';
import { GoogleLogin } from '@react-oauth/google';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

const DEFAULT_AI_MSG = { sender: 'ai', text: 'Hello! How can I help you study today?' };

function App() {
  const [jwt, setJwt] = useState(() => localStorage.getItem('ai_study_helper_jwt'));
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [image, setImage] = useState(null);

  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');

  // Persist theme
  useEffect(() => {
    document.body.classList.toggle('dark-theme', theme === 'dark');
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Helper: Fetch with automatic token refresh
  async function fetchWithAuth(url, options = {}) {
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
          setJwt(data.access_token);
          options.headers['Authorization'] = `Bearer ${data.access_token}`;
          res = await fetch(url, options);
        }
      }
    }
    return res;
  }

  // Load chat sessions after login
  useEffect(() => {
    if (!jwt) return;
    fetchWithAuth('http://localhost:8000/chat/sessions')
      .then(res => res.json())
      .then(data => {
        setSessions(data);
        if (data.length > 0) setSelectedSession(data[0].id);
      });
  }, [jwt]);

  // Load chat history when session changes
  useEffect(() => {
    if (!jwt || !selectedSession) return;
    fetchWithAuth(`http://localhost:8000/chat/history?session_id=${selectedSession}`)
      .then(res => res.json())
      .then(data => setMessages(Array.isArray(data) && data.length ? data : [DEFAULT_AI_MSG]))
      .catch(() => setMessages([DEFAULT_AI_MSG]));
  }, [jwt, selectedSession]);

  const handleImageChange = e => e.target.files && setImage(e.target.files[0]);

  const handleSend = async () => {
    if (!input.trim() && !image) return;

    const userMsgText = input.trim()
      ? image
        ? `${input} [Image attached: ${image.name}]`
        : input
      : `[Image attached: ${image.name}]`;

    setMessages(msgs => [...msgs, { sender: 'user', text: userMsgText }]);
    setLoading(true);

    try {
      const formData = new FormData();
      if (input.trim()) formData.append('message', input);
      if (image) formData.append('file', image);
      if (jwt && selectedSession) formData.append('session_id', selectedSession);

      const res = await fetchWithAuth('http://localhost:8000/chat/ask', {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      setMessages(msgs => [
        ...msgs,
        { sender: 'ai', text: data.response || data.error || 'Error: No response from server.' },
      ]);
    } catch {
      setMessages(msgs => [...msgs, { sender: 'ai', text: 'Error: Could not reach server.' }]);
    } finally {
      setInput('');
      setImage(null);
      setLoading(false);
    }
  };

  const handleKeyDown = e => e.key === 'Enter' && handleSend();

  const handleLogout = () => {
    localStorage.clear();
    setJwt(null);
    setMessages([]);
  };

  const ThemeToggle = () => (
    <button
      className="theme-toggle-btn"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle dark/light mode"
    >
      {theme === 'dark' ? '🌙 Dark' : '☀️ Light'}
    </button>
  );

  if (!jwt) {
    return (
      <div className="App login-container">
        <h2>AI Study Helper Login</h2>
        <div className="login-google">
          <GoogleLogin
            onSuccess={async res => {
              const idToken = res.credential;
              const response = await fetch('http://localhost:8000/auth/google', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: idToken }),
              });
              const data = await response.json();
              if (data.access_token) {
                localStorage.setItem('ai_study_helper_jwt', data.access_token);
                setJwt(data.access_token);
              } else {
                alert('Login failed: ' + (data.detail || data.msg || 'Unknown error'));
              }
            }}
            onError={() => alert('Google login failed')}
          />
        </div>
        <div className="login-note">
          <p>Only registered users can use the app. Please sign in with Google to continue.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="App app-main">
      <div className="sidebar">
        <h3 className="sidebar-title">Chats</h3>
        <ul className="sidebar-list">
          {sessions.map(session => (
            <li key={session.id} className="sidebar-list-item">
              <button
                className={`sidebar-chat-btn${selectedSession === session.id ? ' selected' : ''}`}
                onClick={() => setSelectedSession(session.id)}
              >
                {session.title || 'New Chat'}
              </button>
            </li>
          ))}
        </ul>
        <button
          className="sidebar-newchat-btn"
          onClick={async () => {
            const title = prompt('Enter a title for the new chat:') || 'New Chat';
            const res = await fetch('http://localhost:8000/chat/sessions', {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${jwt}`, 'Content-Type': 'application/json' },
              body: JSON.stringify({ title }),
            });
            const data = await res.json();
            if (data?.id) {
              setSessions(s => [data, ...s]);
              setSelectedSession(data.id);
            }
          }}
        >
          + New Chat
        </button>
        <div className="sidebar-bottom">
          <ThemeToggle />
          <button onClick={handleLogout} className="logout-btn" style={{ width: '100%' }}>
            Logout
          </button>
        </div>
      </div>

      <div className="chat-main">
        <div className="chat-history">
          {messages.map((msg, idx) =>
            msg.sender === 'user' ? (
              <div key={idx} className="chat-message user">
                {msg.text}
              </div>
            ) : (
              <div key={idx} className="chat-message ai">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {msg.text}
                </ReactMarkdown>
              </div>
            )
          )}
          {loading && <div className="chat-typing">AI is typing...</div>}
        </div>

        <div className="chat-input-row">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your question..."
            className="chat-input"
            disabled={loading}
          />
          <input type="file" accept="image/*" onChange={handleImageChange} className="chat-file-input" disabled={loading} />
          {image && <span className="chat-image-name">{image.name}</span>}
          <button
            onClick={handleSend}
            disabled={loading || (!input.trim() && !image)}
            className="chat-send-btn"
          >
            {loading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;

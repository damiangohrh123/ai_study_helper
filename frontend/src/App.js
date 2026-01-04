import React, { useState } from 'react';
import './App.css';
import { GoogleLogin } from '@react-oauth/google';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

function App() {
  const [jwt, setJwt] = useState(() => localStorage.getItem('ai_study_helper_jwt') || null);
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
    if (jwt) {
      fetchWithAuth('http://localhost:8000/chat/sessions', {}, setJwt)
        .then(res => res.json())
        .then(data => {
          setSessions(data);
          if (data.length > 0) {
            setSelectedSession(data[0].id);
          }
        });
    }
  }, [jwt]);

  // Fetch chat history for selected session
  React.useEffect(() => {
    if (jwt && selectedSession) {
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
  }, [jwt, selectedSession]);
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
      if (jwt && selectedSession) formData.append('session_id', selectedSession);
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

  if (!jwt) {
    return (
      <div className="App login-container">
        <h2>AI Study Helper Login</h2>
        <div className="login-google">
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
              } else {
                alert('Google login failed: ' + (data.detail || data.msg || 'Unknown error'));
              }
            }}
            onError={() => {
              alert('Google login failed');
            }}
          />
        </div>
        <div className="login-note">
          <p>Only registered users can use the app. Please sign in with Google to continue.</p>
        </div>
      </div>
    );
  }

  // Chat UI (shown after login)
  const handleLogout = () => {
    localStorage.clear();
    setJwt(null);
    setMessages([]);
  };
  return (
    <div className="App app-main">
      {/* Always show sidebar */}
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
      <div className="chat-main">
        <h2 className="chat-title">AI Study Helper</h2>
        <button onClick={handleLogout} className="logout-btn">Logout</button>
        <div className="chat-history">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`chat-message${msg.sender === 'user' ? ' user' : ' ai'}`}
            >
              <span className={`chat-message-label${msg.sender === 'user' ? ' user' : ' ai'}`}> 
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
          <input
            type="file"
            accept="image/*"
            onChange={handleImageChange}
            className="chat-file-input"
            disabled={imageUploading}
          />
          {image && <span className="chat-image-name">{image.name}</span>}
          <button onClick={handleSend} disabled={loading || imageUploading || (!input.trim() && !image)} className="chat-send-btn">
            {loading || imageUploading ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default App;

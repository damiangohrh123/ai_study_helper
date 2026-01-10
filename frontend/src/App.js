// App.js
// Main application component. Handles layout, theme, chat session state, and integrates all major modules.
// Uses AuthContext for authentication and fetchWithAuth for API calls.
import React, { useState, useEffect } from 'react';
import { fetchWithAuth } from './api';
import { AuthProvider, useAuth } from './AuthContext';
import './App.css';
import Login from './Login';
import 'katex/dist/katex.min.css';
import Sidebar from './Sidebar';
import ChatMain from './ChatMain';

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function AppInner() {
  const { jwt, setJwt, logout } = useAuth();

  // Chat & session state
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [image, setImage] = useState(null);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');

  // Theme state
  useEffect(() => {
    document.body.classList.toggle('dark-theme', theme === 'dark');
    localStorage.setItem('theme', theme);
  }, [theme]);

  // Load chat sessions after login
  useEffect(() => {
    if (!jwt) return;
    fetchWithAuth(`${BASE_URL}/chat/sessions`, {}, setJwt)
      .then(res => res.json())
      .then(data => {
        setSessions(data);
        if (data.length > 0) setSelectedSession(data[0].id);
      })
      .catch(err => {
        if (err.message === 'Session expired. Please log in again.') {
          logout();
          alert('Session expired. Please log in again.');
        }
      });
  }, [jwt, setJwt, logout]);

  // Load chat history when session changes
  useEffect(() => {
    if (!jwt || !selectedSession) return;
    fetchWithAuth(`${BASE_URL}/chat/history?session_id=${selectedSession}`, {}, setJwt)
      .then(res => res.json())
      .then(data => setMessages(Array.isArray(data) && data.length ? data : []))
      .catch(err => {
        if (err.message === 'Session expired. Please log in again.') {
          logout();
          alert('Session expired. Please log in again.');
        } else {
          setMessages([]);
        }
      });
  }, [jwt, selectedSession, setJwt, logout]);

  // Image file selection
  const handleImageChange = e => e.target.files && setImage(e.target.files[0]);

  // Send user message (text + optional image)
  const handleSend = async () => {
    // Do nothing if both text and image are empty
    if (!input.trim() && !image) return;

    let userMsgText = '';

    if (input.trim() && image) userMsgText = `${input} [Image attached: ${image.name}]`; // Text and image
    else if (input.trim()) userMsgText = input;                                          // Text only
    else if (image) userMsgText = `[Image attached: ${image.name}]`;                     // Image only

    // Add the user message to messages state
    setMessages(msgs => [...msgs, { sender: 'user', text: userMsgText }]);

    // Show loading state
    setLoading(true);

    try {
      const formData = new FormData();
      if (input.trim()) formData.append('message', input);
      if (image) formData.append('file', image);
      if (jwt && selectedSession) formData.append('session_id', selectedSession);

      const res = await fetchWithAuth(`${BASE_URL}/chat/ask`, {
        method: 'POST',
        body: formData,
      }, setJwt);

      const data = await res.json();
      setMessages(msgs => [
        ...msgs,
        { sender: 'ai', text: data.response || data.error || 'Error: No response from server.' },
      ]);
    } catch (err) {
      if (err.message === 'Session expired. Please log in again.') {
        logout();
        alert('Session expired. Please log in again.');
      } else {
        setMessages(msgs => [...msgs, { sender: 'ai', text: 'Error: Could not reach server.' }]);
      }
    } finally {
      setInput('');
      setImage(null);
      setLoading(false);
    }
  };

  const handleKeyDown = e => e.key === 'Enter' && handleSend();

  const handleLogout = () => {
    logout();
    setMessages([]);
  };

  const ThemeToggle = () => (
    <button
      className="theme-toggle-btn"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle dark/light mode"
    >
      {theme === 'dark' ? 'Dark' : 'Light'}
    </button>
  );

  if (!jwt) {
    return <Login setJwt={setJwt} />;
  }

  const handleNewChat = async () => {
    const title = prompt('Enter a title for the new chat:') || 'New Chat';
    const res = await fetch(`${BASE_URL}/chat/sessions`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${jwt}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    const data = await res.json();
    if (data?.id) {
      setSessions(s => [data, ...s]);
      setSelectedSession(data.id);
    }
  };

    return (
      <div className="App app-main">
        <Sidebar
          sessions={sessions}
          setSessions={setSessions}
          selectedSession={selectedSession}
          setSelectedSession={setSelectedSession}
          handleNewChat={handleNewChat}
          ThemeToggle={ThemeToggle}
          handleLogout={handleLogout}
          setJwt={setJwt}
        />
        <ChatMain
          messages={messages}
          loading={loading}
          input={input}
          setInput={setInput}
          handleKeyDown={handleKeyDown}
          handleImageChange={handleImageChange}
          image={image}
          handleSend={handleSend}
        />
      </div>
    );
  }

  function App() {
    return (
      <AuthProvider>
        <AppInner />
      </AuthProvider>
    );
  }

export default App;
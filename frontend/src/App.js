// App.js
import React, { useState, useEffect } from 'react';
import { fetchWithAuth } from './api';
import { AuthProvider, useAuth } from './AuthContext';
import './App.css';
import Login from './Login';
import Sidebar from './Sidebar';
import ChatMain from './ChatMain';
import ProfilePage from './ProfilePage';
import 'katex/dist/katex.min.css';

const BASE_URL = process.env.REACT_APP_API_URL;

function AppInner() {
  const { jwt, setJwt, logout } = useAuth();
  const [activeView, setActiveView] = useState('chat');
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [image, setImage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');

  useEffect(() => {
    document.body.classList.toggle('dark-theme', theme === 'dark');
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!jwt) return;
    fetchWithAuth(`${BASE_URL}/chat/sessions`, {}, setJwt, logout)
      .then(res => res.json())
      .then(data => {
        setSessions(data);
        if (data.length) setSelectedSession(data[0].id);
      })
      .catch(() => {});
  }, [jwt, setJwt, logout]);

  useEffect(() => {
    if (!jwt || !selectedSession || activeView !== 'chat') return;
    fetchWithAuth(
      `${BASE_URL}/chat/history?session_id=${selectedSession}`,
      {}, setJwt, logout
    )
      .then(res => res.json())
      .then(data => setMessages(Array.isArray(data) ? data : []))
      .catch(() => setMessages([]));
  }, [jwt, selectedSession, activeView, setJwt, logout]);

  const hasUnansweredQuiz = () => {
    if (!messages.length) return false;
    const last = messages[messages.length - 1];
    return last.sender === 'ai' && last.type === 'quiz_question';
  };

  // Unified message sending logic
  const sendMessage = async (formData, isQuiz = false, userText = '') => {
    setLoading(true);
    try {
      const res = await fetchWithAuth(
        `${BASE_URL}/chat/ask`,
        { method: 'POST', body: formData },
        setJwt,
        logout
      );
      const data = await res.json();
      if (data.message_type === 'quiz_lock') {
        alert(data.response || 'Please answer the current quiz question first.');
        setLoading(false);
        return false;
      }
      setMessages(msgs => [
        ...msgs,
        ...(isQuiz ? [{ sender: 'user', text: userText }] : []),
        { sender: 'ai', text: data.response, type: data.message_type }
      ]);
      return true;
    } catch {
      setMessages(msgs => [...msgs, { sender: 'ai', text: isQuiz ? 'Quiz failed.' : 'Server error.' }]);
      return false;
    } finally {
      setInput('');
      setImage(null);
      setLoading(false);
    }
  };

  const handleSend = async () => {
    if (!input.trim() && !image) return;
    const formData = new FormData();
    formData.append('session_id', selectedSession);
    if (input.trim()) formData.append('message', input);
    if (image) formData.append('file', image);
    setMessages(msgs => [...msgs, { sender: 'user', text: input }]);
    await sendMessage(formData, false);
  };

  const handleQuizClick = async () => {
    if (!selectedSession || loading) return;
    if (hasUnansweredQuiz()) {
      alert('Please answer the current quiz question first.');
      return;
    }
    setMessages(msgs => [...msgs, { sender: 'user', text: 'Quiz Me!' }]);
    const formData = new FormData();
    formData.append('message', '');
    formData.append('session_id', selectedSession);
    formData.append('action', 'quiz');
    await sendMessage(formData, false); // Don't add user message again in sendMessage
  };

  const handleNewChat = async () => {
    const title = prompt('Chat title') || 'New Chat';
    const res = await fetchWithAuth(
      `${BASE_URL}/chat/sessions`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
      },
      setJwt,
      logout
    );
    const data = await res.json();
    if (data?.id) {
      setSessions(s => [data, ...s]);
      setSelectedSession(data.id);
      setMessages([]);
    }
  };

  if (!jwt) return <Login setJwt={setJwt} />;

  return (
    <div className="App app-main">
      <Sidebar
        sessions={sessions}
        setSessions={setSessions}
        selectedSession={selectedSession}
        setSelectedSession={setSelectedSession}
        handleNewChat={handleNewChat}
        handleLogout={logout}
        setJwt={setJwt}
        activeView={activeView}
        setActiveView={setActiveView}
      />
      {activeView === 'profile' ? (
        <ProfilePage theme={theme} setTheme={setTheme} />
      ) : (
        <ChatMain
          messages={messages}
          input={input}
          setInput={setInput}
          image={image}
          setImage={setImage}
          loading={loading}
          handleSend={handleSend}
          handleKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          onQuizClick={handleQuizClick}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}
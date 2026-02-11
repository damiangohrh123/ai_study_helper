// Sidebar.js
// Renders the sidebar with chat sessions, new chat button, and logout.
import React, { useState, useEffect, useRef } from 'react';
import { renameChatSession, deleteChatSession } from './api';

function Sidebar({
  sessions,
  setSessions,
  selectedSession,
  setSelectedSession,
  handleNewChat,
  handleLogout,
  setJwt,
  activeView,
  setActiveView
}) {

  const [menuOpenId, setMenuOpenId] = useState(null);
  const menuBtnRefs = useRef({});
  const popupRefs = useRef({});

  useEffect(() => {
    if (menuOpenId === null) return;
    function handleClickOutside(e) {
      // If click is outside both the menu button and the popup, close
      const btn = menuBtnRefs.current[menuOpenId];
      const popup = popupRefs.current[menuOpenId];
      if (
        btn && !btn.contains(e.target) &&
        popup && !popup.contains(e.target)
      ) {
        setMenuOpenId(null);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [menuOpenId]);

  const handleMenuClick = (sessionId) => {
    setMenuOpenId(menuOpenId === sessionId ? null : sessionId);
  };

  // Rename chat handler
  const handleRename = async (sessionId) => {
    const current = sessions.find(s => s.id === sessionId);
    const newTitle = prompt('Rename chat:', current?.title || '');
    if (!newTitle || newTitle === current?.title) return setMenuOpenId(null);
    try {
      const res = await renameChatSession(sessionId, newTitle, setJwt);
      if (res.ok) {
        const updated = await res.json();
        setSessions(sessions.map(s => s.id === sessionId ? { ...s, title: updated.title } : s));
      } else {
        alert('Failed to rename chat.');
      }
    } catch {
      alert('Error renaming chat.');
    }
    setMenuOpenId(null);
  };

  // Delete chat handler
  const handleDelete = async (sessionId) => {
    if (!window.confirm('Delete this chat? This cannot be undone.')) return setMenuOpenId(null);
    try {
      await deleteChatSession(sessionId, setJwt);
      setSessions(sessions.filter(s => s.id !== sessionId));
      if (selectedSession === sessionId) {
        // Select another session if possible
        const remaining = sessions.filter(s => s.id !== sessionId);
        setSelectedSession(remaining.length ? remaining[0].id : null);
      }
    } catch (err) {
      // Only show error if truly thrown (network or backend error)
      alert(err?.message || 'Error deleting chat.');
    }
    setMenuOpenId(null);
  };

  return (
    <div className="sidebar">
      <h3 className="sidebar-title">AI Study Helper</h3>
      <ul className="sidebar-list">
        {sessions.map(session => (
          <li key={session.id} className="sidebar-list-item" style={{ position: 'relative' }}>
            <button
              className={`sidebar-chat-btn${activeView === 'chat' && selectedSession === session.id ? ' selected' : ''}`}
              onClick={() => {
                setActiveView('chat');
                setSelectedSession(session.id);
              }}
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            >
              <span>{session.title || 'New Chat'}</span>
              <span
                className="sidebar-chat-menu-btn"
                ref={el => (menuBtnRefs.current[session.id] = el)}
                onClick={e => { e.stopPropagation(); handleMenuClick(session.id); }}
                aria-label="Chat options"
                tabIndex={0}
                style={{ marginLeft: '8px', display: 'flex', alignItems: 'center' }}
              >
                <span className="sidebar-chat-menu-icon">⋯</span>
              </span>
            </button>
            {menuOpenId === session.id && (
              <div
                className="sidebar-chat-popup"
                ref={el => (popupRefs.current[session.id] = el)}
              >
                <button className="sidebar-chat-popup-btn" onClick={() => handleRename(session.id)}>Rename</button>
                <button className="sidebar-chat-popup-btn" onClick={() => handleDelete(session.id)}>Delete</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      <button
        className="sidebar-newchat-btn"
        onClick={handleNewChat}
      >
        + New Chat
      </button>
      <button
        className="sidebar-profile-btn"
        style={{ width: '100%', marginTop: 12 }}
        onClick={() => setActiveView('profile')}
      >
        Profile
      </button>
      <div className="sidebar-bottom">
        <button onClick={handleLogout} className="logout-btn" style={{ width: '100%' }}>
          Logout
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
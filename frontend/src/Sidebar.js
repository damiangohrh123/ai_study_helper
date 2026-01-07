// Sidebar.js
// Renders the sidebar with chat sessions, new chat button, theme toggle, and logout.
import React, { useState, useEffect, useRef } from 'react';

function Sidebar({
  sessions,
  selectedSession,
  setSelectedSession,
  handleNewChat,
  ThemeToggle,
  handleLogout
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

  const handleCloseMenu = () => setMenuOpenId(null);

  return (
    <div className="sidebar">
      <h3 className="sidebar-title">AI Study Helper</h3>
      
      <ul className="sidebar-list">
        {sessions.map(session => (
          <li key={session.id} className="sidebar-list-item" style={{ position: 'relative' }}>
            <button
              className={`sidebar-chat-btn${selectedSession === session.id ? ' selected' : ''}`}
              onClick={() => setSelectedSession(session.id)}
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
                <button className="sidebar-chat-popup-btn" onClick={handleCloseMenu}>Rename</button>
                <button className="sidebar-chat-popup-btn" onClick={handleCloseMenu}>Delete</button>
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
      <div className="sidebar-bottom">
        <ThemeToggle />
        <button onClick={handleLogout} className="logout-btn" style={{ width: '100%' }}>
          Logout
        </button>
      </div>
    </div>
  );
}

export default Sidebar;
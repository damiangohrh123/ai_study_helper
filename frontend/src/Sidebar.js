// Sidebar.js
// Renders the sidebar with chat sessions, new chat button, theme toggle, and logout.
function Sidebar({
  sessions,
  selectedSession,
  setSelectedSession,
  handleNewChat,
  ThemeToggle,
  handleLogout
}) {
  return (
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
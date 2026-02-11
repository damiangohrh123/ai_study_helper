// ProfilePage.js

function ThemeToggle({ theme, setTheme }) {
  return (
    <button
      className="theme-toggle-btn"
      onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      aria-label="Toggle dark/light mode"
    >
      {theme === 'dark' ? 'Dark' : 'Light'}
    </button>
  );
}

function ProfilePage({ theme, setTheme }) {
  return (
    <div className="profile-page">
      <ThemeToggle theme={theme} setTheme={setTheme} />
    </div>
  );
}

export default ProfilePage;
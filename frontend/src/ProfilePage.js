// ProfilePage.js
// Shows user progress, concept mastery, and recent learning activity.
import React, { useEffect, useState } from 'react';
import { fetchProgress } from './api';

function ProfilePage({ setJwt }) {
  const [progress, setProgress] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const progressData = await fetchProgress(setJwt);
        setProgress(progressData);
      } catch (err) {
        setError(err.message || 'Failed to load profile data');
      } finally {
        setLoading(false);
      }
    })();
  }, [setJwt]);

  // ---------------- Helpers ----------------
  const formatDate = d => new Date(d).toLocaleDateString();

  const formatDelta = delta => {
    if (delta === undefined || delta === null) return null;
    if (delta > 0) return `▲ ${delta.toFixed(1)}`;
    if (delta < 0) return `▼ ${Math.abs(delta).toFixed(1)}`;
    return '-';
  };

  const deltaClass = delta => {
    if (delta > 0) return 'delta-positive';
    if (delta < 0) return 'delta-negative';
    return 'delta-neutral';
  };

  // ---------------- Render states ----------------
  if (loading) return <div className="profile-loading">Loading profile...</div>;
  if (error) return <div className="profile-error">{error}</div>;

  // ---------------- UI ----------------
  return (
    <div className="profile-page">
      <h2>My Progress</h2>

      {/* Subjects */}
      <section className="profile-section">
        <h3>Subjects</h3>
        {progress?.subjects?.length ? (
          <ul className="profile-list">
            {progress.subjects.map((s, i) => (
              <li key={i} className="profile-item">
                <div className="profile-main">
                  <strong>{s.subject}</strong>: {s.learning_skill}
                </div>

                <div className="profile-meta">
                  <span className="profile-date">
                    {formatDate(s.last_updated)}
                  </span>

                  {formatDelta(s.learning_delta) && (
                    <span className={`profile-delta ${deltaClass(s.learning_delta)}`}>
                      {formatDelta(s.learning_delta)}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div>No subject data yet.</div>
        )}
      </section>

      {/* Concepts */}
      <section className="profile-section">
        <h3>Concepts</h3>
        {progress?.concepts?.length ? (
          <ul className="profile-list">
            {progress.concepts.map((c, i) => (
              <li key={i} className="profile-item">
                <div className="profile-main">
                  <strong>{c.subject}</strong> — {c.name || 'Unnamed'}: {c.confidence}
                </div>

                <div className="profile-meta">
                  <span className="profile-date">
                    {formatDate(c.last_seen)}
                  </span>

                  {formatDelta(c.confidence_delta) && (
                    <span className={`profile-delta ${deltaClass(c.confidence_delta)}`}>
                      {formatDelta(c.confidence_delta)}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div>No concept data yet.</div>
        )}
      </section>
    </div>
  );
}

export default ProfilePage;
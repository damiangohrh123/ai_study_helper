// ProfilePage.js
// Shows user progress, concept mastery, and recent learning activity.
import React, { useEffect, useState } from 'react';
import { fetchProgress, fetchReflection } from './api';

function ProfilePage({ setJwt }) {
  const [progress, setProgress] = useState(null);
  const [reflection, setReflection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [progressData, reflectionData] = await Promise.all([
          fetchProgress(setJwt),
          fetchReflection(setJwt),
        ]);
        setProgress(progressData);
        setReflection(reflectionData);
      } catch (err) {
        setError(err.message || 'Failed to load profile data');
      } finally {
        setLoading(false);
      }
    })();
  }, [setJwt]);

  // Date formatting helpers
  const formatDate = d => new Date(d).toLocaleDateString();
  const formatDateTime = d => new Date(d).toLocaleString();

  if (loading) return <div className="profile-loading">Loading profile...</div>;
  if (error) return <div className="profile-error">{error}</div>;

  return (
    <div className="profile-page">
      <h2>My Progress</h2>
      <section className="profile-section">
        <h3>Subjects</h3>
        {progress?.subjects?.length ? (
          <ul>
            {progress.subjects.map((s, i) => (
              <li key={i}>
                <strong>{s.subject}:</strong> {s.learning_skill} <span className="profile-date">({formatDate(s.last_updated)})</span>
              </li>
            ))}
          </ul>
        ) : <div>No subject data yet.</div>}
      </section>
      <section className="profile-section">
        <h3>Concepts</h3>
        {progress?.concepts?.length ? (
          <ul>
            {progress.concepts.map((c, i) => (
              <li key={i}>
                <strong>{c.subject}</strong> - {c.name || 'Unnamed'}: {c.confidence} <span className="profile-date">({formatDate(c.last_seen)})</span>
              </li>
            ))}
          </ul>
        ) : <div>No concept data yet.</div>}
      </section>
      <section className="profile-section">
        <h3>Recent Learning Activity</h3>
        {reflection?.signals?.length ? (
          <ul>
            {reflection.signals.map((sig, i) => (
              <li key={i}>
                <strong>{sig.type}</strong> <span className="profile-date">{formatDateTime(sig.timestamp)}</span>
              </li>
            ))}
          </ul>
        ) : <div>No recent activity.</div>}
      </section>
    </div>
  );
}

export default ProfilePage;
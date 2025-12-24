
import React, { useState } from 'react';
import './App.css';

function App() {
  const [messages, setMessages] = useState([
    { sender: 'ai', text: 'Hello! How can I help you study today?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = async () => {
    if (!input.trim()) return;
    const userMsg = { sender: 'user', text: input };
    setMessages(msgs => [...msgs, userMsg]);
    setLoading(true);
    setInput('');
    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: input })
      });
      const data = await res.json();
      setMessages(msgs => [...msgs, { sender: 'ai', text: data.response }]);
    } catch (err) {
      setMessages(msgs => [...msgs, { sender: 'ai', text: 'Error: Could not reach server.' }]);
    }
    setLoading(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSend();
  };

  return (
    <div className="App" style={{ maxWidth: 500, margin: '40px auto', padding: 20 }}>
      <h2>AI Study Helper</h2>
      <div style={{ border: '1px solid #ccc', borderRadius: 8, padding: 16, minHeight: 200, background: '#fafafa', marginBottom: 16 }}>
        {messages.map((msg, idx) => (
          <div key={idx} style={{ textAlign: msg.sender === 'user' ? 'right' : 'left', margin: '8px 0' }}>
            <span style={{ fontWeight: msg.sender === 'user' ? 'bold' : 'normal' }}>
              {msg.sender === 'user' ? 'You' : 'AI'}:
            </span> {msg.text}
          </div>
        ))}
        {loading && <div style={{ color: '#888' }}>AI is typing...</div>}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your question..."
          style={{ flex: 1, padding: 8, borderRadius: 4, border: '1px solid #ccc' }}
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || !input.trim()} style={{ padding: '8px 16px' }}>
          Send
        </button>
      </div>
    </div>
  );
}

export default App;

// ChatMain.js
// Main chat area. Displays chat history, welcome text, input box, and handles sending messages.
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

function ChatMain({
  messages,
  loading,
  input,
  setInput,
  handleKeyDown,
  handleImageChange,
  image,
  handleSend
}) {
  return (
    <div className="chat-main">
      <h2 className="chat-title">AI Study Helper</h2>
      <div className="chat-history">
        {messages.length === 0 ? (
          <div className="chat-welcome-text">
            Hello! How can I help you study today?
          </div>
        ) : (
          messages.map((msg, idx) =>
            msg.sender === 'user' ? (
              <div key={idx} className="chat-message user">
                {msg.text}
              </div>
            ) : (
              <div key={idx} className="chat-message ai">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {msg.text}
                </ReactMarkdown>
              </div>
            )
          )
        )}
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
        <input type="file" accept="image/*" onChange={handleImageChange} className="chat-file-input" disabled={loading} />
        {image && <span className="chat-image-name">{image.name}</span>}
        <button
          onClick={handleSend}
          disabled={loading || (!input.trim() && !image)}
          className="chat-send-btn"
        >
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  );
}

export default ChatMain;
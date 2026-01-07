// ChatMain.js
// Main chat area. Displays chat history, welcome text, input box, and handles sending messages.
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

// Remove bold/italic around math
function cleanMathBold(text = '') {
  text = text.replace(/(\*\*|__|\*|_)\s*(\\\([\s\S]+?\\\))\s*(\*\*|__|\*|_)/g, '$2');
  text = text.replace(/(\*\*|__|\*|_)\s*(\\\[[\s\S]+?\\\])\s*(\*\*|__|\*|_)/g, '$2');
  return text;
}

// Normalize LaTeX to single-line $ ... $ for ReactMarkdown + KaTeX
function normalizeLatex(text = '') {
  let cleaned = text;

  // Remove bold/italic first
  cleaned = cleanMathBold(cleaned);

  // Convert block math \[ ... \] → $ ... $
  cleaned = cleaned.replace(/\\\[([\s\S]+?)\\\]/g, (match, p1) => `$  ${p1.trim()}  $`);

  // Convert inline math \( ... \) → $ ... $
  cleaned = cleaned.replace(/\\\(([\s\S]+?)\\\)/g, (match, p1) => `$  ${p1.trim()}  $`);

  // Normalize multiple newlines
  cleaned = cleaned.replace(/\n{2,}/g, '\n\n');

  // Trim trailing spaces from each line
  cleaned = cleaned
    .split('\n')
    .map(line => line.trimEnd())
    .join('\n');

  return cleaned;
}

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

      <div className="chat-history">
        {messages.length === 0 ? (
          <div className="chat-welcome-text">
            Hello! How can I help you study today?
          </div>
        ) : (
          messages.map((msg, idx) => {
            const isUser = msg.sender === 'user';
            const content = isUser ? msg.text : normalizeLatex(msg.text);

            // Console logs for debugging
            if (!isUser) console.log("Raw text: \n", msg.text);
            if (!isUser) console.log("Preprocessed content: \n", content);

            return (
              <div key={idx} className={`chat-message ${isUser ? 'user' : 'ai'}`}>
                {isUser ? (
                  msg.text
                ) : (
                  <ReactMarkdown
                    remarkPlugins={[remarkMath]}
                    rehypePlugins={[rehypeKatex]}
                  >
                    {content}
                  </ReactMarkdown>
                )}
              </div>
            );
          })
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

        <input
          type="file"
          accept="image/*"
          onChange={handleImageChange}
          className="chat-file-input"
          disabled={loading}
        />

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
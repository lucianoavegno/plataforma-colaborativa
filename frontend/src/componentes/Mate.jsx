import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

/** Renderiza markdown con LaTeX: $...$ en línea, $$...$$ en bloque. */
export default function Mate({ children, className = '' }) {
  return (
    <div className={`mate ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children || ''}
      </ReactMarkdown>
    </div>
  );
}

import React, { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';

window.addEventListener('unhandledrejection', (event) => {
  const msg = String(event.reason?.message || event.reason || '');
  if (msg.includes('WebSocket closed without opened') || msg.includes('vite')) {
    event.preventDefault();
  }
});

class RootErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[Bitsure RootErrorBoundary]', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen bg-[#090D16] text-[#F1F5F9] flex items-center justify-center p-6 font-sans">
          <div className="max-w-lg w-full bg-[#111827] border border-white/15 rounded-xl p-6 space-y-4">
            <h2 className="text-base font-bold text-[#F43F5E]">
              Une erreur d&apos;affichage a été interceptée
            </h2>
            <p className="text-xs text-[#94A3B8] font-mono break-words bg-[#090D16] p-3 rounded border border-white/10">
              {String(this.state.error?.message || this.state.error)}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  this.setState({ error: null });
                  window.location.reload();
                }}
                className="px-4 py-2 bg-[#10B981] text-[#090D16] text-xs font-semibold rounded-lg"
              >
                Recharger l&apos;interface
              </button>
              <button
                type="button"
                onClick={() => {
                  try {
                    localStorage.removeItem('bitsure_session_token');
                    localStorage.removeItem('bitsure_csrf_token');
                  } catch {
                    // ignore
                  }
                  window.location.href = '/';
                }}
                className="px-4 py-2 bg-[#1E293B] border border-white/10 text-[#F1F5F9] text-xs font-semibold rounded-lg"
              >
                Réinitialiser la session locale
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </StrictMode>
);


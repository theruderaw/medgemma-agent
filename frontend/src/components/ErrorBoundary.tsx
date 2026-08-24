import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  /** Rendered in place of the failed subtree; typically a retry affordance. */
  fallback?: (message: string, reset: () => void) => ReactNode;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time exceptions in its subtree so one broken component
 * cannot white-screen the whole app. Reset re-renders the subtree (e.g.
 * after the user navigates away from the bad state).
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (error) {
      return (
        this.props.fallback?.(error.message, this.reset) ?? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
            <p className="text-sm text-neutral-500 dark:text-neutral-400">
              Something went wrong — please refresh to continue.
            </p>
            <button
              type="button"
              onClick={this.reset}
              className="cursor-pointer rounded-lg border border-neutral-300 px-4 py-2 text-sm text-neutral-600 transition-colors hover:border-neutral-500 hover:text-neutral-900 dark:border-neutral-700 dark:text-neutral-300 dark:hover:text-neutral-100"
            >
              Try again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
    children?: ReactNode;
    fallbackTitle?: string;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

class ErrorBoundary extends Component<Props, State> {
    public readonly state: State = {
        hasError: false,
        error: null
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error("Uncaught error:", error, errorInfo);
    }

    public handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    public render() {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center h-full p-8 text-center space-y-4 bg-[#09090b]">
                    <div className="p-4 bg-red-500/10 rounded-full">
                        <AlertTriangle size={32} className="text-red-500" />
                    </div>
                    <div>
                        <h2 className="text-xl font-bold text-white mb-2">
                            {this.props.fallbackTitle || "Something went wrong"}
                        </h2>
                        <p className="text-slate-400 max-w-sm mx-auto text-sm mb-4">
                            {this.state.error?.message || "An unexpected error occurred while loading this component."}
                        </p>
                        <button
                            onClick={this.handleReset}
                            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold transition-colors mx-auto"
                        >
                            <RefreshCw size={16} />
                            Try Again
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;

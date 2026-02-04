import React, { createContext, useContext, useEffect, useState } from 'react';
import { X, AlertCircle, AlertTriangle, CheckCircle, Info } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastMessage {
    id: string;
    type: ToastType;
    title: string;
    message: string;
    action?: string; // e.g. "contact_admin", "retry"
}

interface ToastContextType {
    showToast: (type: ToastType, title: string, message: string, action?: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [toasts, setToasts] = useState<ToastMessage[]>([]);

    useEffect(() => {
        // Listen for global custom events from non-React code (e.g. dataService)
        const handleGlobalToast = (e: CustomEvent) => {
            const { type, title, message, action } = e.detail;
            addToast(type, title, message, action);
        };

        window.addEventListener('omnihub-toast' as any, handleGlobalToast);
        return () => window.removeEventListener('omnihub-toast' as any, handleGlobalToast);
    }, []);

    const addToast = (type: ToastType, title: string, message: string, action?: string) => {
        const id = Math.random().toString(36).substring(2, 9);
        setToasts(prev => [...prev, { id, type, title, message, action }]);

        // Auto dismiss
        setTimeout(() => {
            removeToast(id);
        }, 5000);
    };

    const removeToast = (id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    };

    return (
        <ToastContext.Provider value={{ showToast: addToast }}>
            {children}
            {/* Toast Container */}
            <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none">
                {toasts.map(toast => (
                    <div
                        key={toast.id}
                        className={`pointer-events-auto min-w-[320px] max-w-[400px] backdrop-blur-md rounded-xl border shadow-2xl p-4 animate-in slide-in-from-right fade-in duration-300 ${toast.type === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-200' :
                                toast.type === 'success' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-200' :
                                    toast.type === 'warning' ? 'bg-amber-500/10 border-amber-500/20 text-amber-200' :
                                        'bg-blue-500/10 border-blue-500/20 text-blue-200'
                            }`}
                    >
                        <div className="flex items-start gap-3">
                            <div className={`mt-0.5 p-1 rounded-full ${toast.type === 'error' ? 'bg-red-500/20 text-red-400' :
                                    toast.type === 'success' ? 'bg-emerald-500/20 text-emerald-400' :
                                        toast.type === 'warning' ? 'bg-amber-500/20 text-amber-400' :
                                            'bg-blue-500/20 text-blue-400'
                                }`}>
                                {toast.type === 'error' && <AlertCircle size={16} />}
                                {toast.type === 'success' && <CheckCircle size={16} />}
                                {toast.type === 'warning' && <AlertTriangle size={16} />}
                                {toast.type === 'info' && <Info size={16} />}
                            </div>
                            <div className="flex-1">
                                <h4 className="font-bold text-sm mb-1">{toast.title}</h4>
                                <p className="text-xs opacity-90 leading-relaxed">{toast.message}</p>
                                {toast.action === 'contact_admin' && (
                                    <div className="mt-2 text-[10px] font-bold bg-red-500/20 text-red-300 inline-block px-2 py-1 rounded">
                                        🚨 Please contact IT Support
                                    </div>
                                )}
                            </div>
                            <button
                                onClick={() => removeToast(toast.id)}
                                className="p-1 hover:bg-white/10 rounded-lg transition-colors"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
};

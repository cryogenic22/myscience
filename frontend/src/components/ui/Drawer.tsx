import { X } from 'lucide-react';
import { type ReactNode, useEffect } from 'react';

interface DrawerProps {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    subtitle?: string;
    children: ReactNode;
    width?: string;
}

export function Drawer({ isOpen, onClose, title, subtitle, children, width }: DrawerProps) {
    const resolvedWidth = width ?? 'clamp(320px, 40vw, 600px)';
    // Close on escape
    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handleEsc);
        return () => window.removeEventListener('keydown', handleEsc);
    }, [onClose]);

    if (!isOpen) return null;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-slate-900/10 backdrop-blur-[1px] z-40 transition-opacity"
                onClick={onClose}
            />

            {/* Drawer Panel */}
            <div
                className="fixed inset-y-0 right-0 z-50 flex animate-slide-in flex-col bg-white/96 shadow-2xl"
                style={{ width: resolvedWidth, maxWidth: '94vw' }}
            >
                {/* Header */}
                <div className="flex items-start justify-between bg-white/94 p-5">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
                        {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 -mr-2 text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-5">
                    {children}
                </div>
            </div>
        </>
    );
}

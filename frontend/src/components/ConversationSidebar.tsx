import { MessageSquare, Trash2, X } from 'lucide-react';

interface Conversation {
  id: string;
  title: string;
  savedAt: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  conversations: Conversation[];
  onSelect: (conversation: Conversation) => void;
  onDelete: (id: string) => void;
}

export default function ConversationSidebar({ isOpen, onClose, conversations, onSelect, onDelete }: Props) {
  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-30" onClick={onClose} />

      {/* Sidebar */}
      <div className="absolute inset-y-0 left-0 z-40 flex w-[280px] animate-slide-in flex-col border-r border-slate-200/70 bg-white/96 shadow-lg backdrop-blur-md"
        style={{ animationName: 'slide-in-left' }}
      >
        <div className="flex items-center justify-between border-b border-slate-200/70 px-4 py-3">
          <div className="flex items-center gap-2">
            <MessageSquare size={14} className="text-slate-500" />
            <span className="text-xs font-semibold text-slate-700">Conversations</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          >
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2">
          {conversations.length === 0 ? (
            <div className="mt-4 text-center text-[11px] text-slate-400">
              No saved conversations yet.
              <br />
              Start a chat to create one.
            </div>
          ) : (
            <div className="space-y-1">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className="group flex items-center gap-2 rounded-md px-2.5 py-2 transition-colors hover:bg-slate-50"
                >
                  <button
                    type="button"
                    onClick={() => onSelect(conv)}
                    className="flex-1 min-w-0 text-left"
                  >
                    <div className="truncate text-[11px] font-medium text-slate-700">
                      {conv.title}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {new Date(conv.savedAt).toLocaleDateString()}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(conv.id);
                    }}
                    className="shrink-0 rounded p-1 text-slate-300 opacity-0 transition-all group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-500"
                    title="Delete conversation"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { CitationMark } from '../components/briefs/CitationMark';
import { useBriefAutosave } from '../hooks/useBriefAutosave';
import { PRODUCT_NAME } from '../brand';
import { ThemeToggle } from '../components/primitives/ThemeToggle';

/**
 * PB-401 — Brief composer scaffold.
 *
 * TipTap editor mounted at `/briefs/new`. Ships the editor surface,
 * a custom `{{cite:doc_id}}` mark that renders citation chips, and
 * a 4s-debounced autosave hook. Backend save lands via BE-19; until
 * then `useBriefAutosave` no-ops the network call and just toggles
 * the indicator.
 *
 * Out of scope (own PBs):
 * - PB-402 — inline AI suggestions (Strategist + Curator)
 * - PB-403 — options grid as in-doc primitive
 * - PB-404 — slim sidebar (stakeholders / materiality / state)
 * - PB-405 — migration from legacy DecisionWorkspace
 */

const INITIAL_DOC: Record<string, unknown> = {
  type: 'doc',
  content: [
    {
      type: 'heading',
      attrs: { level: 1 },
      content: [{ type: 'text', text: 'Untitled brief' }],
    },
    {
      type: 'paragraph',
      content: [
        { type: 'text', text: 'Start typing your strategic brief. The editor supports headings, lists, bold, italic, code, and quote blocks.' },
      ],
    },
  ],
};

const CITE_FIXTURE_DOC: Record<string, unknown> = {
  type: 'doc',
  content: [
    {
      type: 'heading',
      attrs: { level: 1 },
      content: [{ type: 'text', text: 'Cite-fixture brief' }],
    },
    {
      type: 'paragraph',
      content: [
        { type: 'text', text: 'Per the SURPASS-PEDS readout ' },
        {
          type: 'text',
          marks: [{ type: 'citation', attrs: { docId: 'doc-1' } }],
          text: '[1]',
        },
        { type: 'text', text: ', the primary endpoint was met.' },
      ],
    },
  ],
};

export default function BriefComposerPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const fixture = params.get('fixture');

  const initialContent = useMemo(
    () => (fixture === 'cite' ? CITE_FIXTURE_DOC : INITIAL_DOC),
    [fixture],
  );

  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder: 'Start writing — / for commands (coming in PB-402)…',
      }),
      CitationMark,
    ],
    content: initialContent,
    immediatelyRender: false,
  });

  // PB-401 uses a synthetic briefId until BE-19 ships the create endpoint.
  const [briefId] = useState<string>(() => `draft-${Date.now()}`);
  const [docJson, setDocJson] = useState<unknown>(initialContent);

  useEffect(() => {
    if (!editor) return;
    const handler = () => setDocJson(editor.getJSON());
    editor.on('update', handler);
    return () => {
      editor.off('update', handler);
    };
  }, [editor]);

  const { status, saveNow } = useBriefAutosave(briefId, docJson);

  const onSaveClick = useCallback(() => {
    void saveNow();
  }, [saveNow]);

  return (
    <div
      className="flex flex-col h-screen"
      style={{ background: 'var(--color-bg)', color: 'var(--color-ink)' }}
    >
      {/* App chrome */}
      <header
        className="shrink-0 flex items-center gap-4"
        style={{
          height: '56px',
          padding: '0 24px',
          borderBottom: '1px solid var(--color-divider)',
          background: 'var(--color-surface)',
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/ci')}
          className="btn-icon"
          aria-label="Back"
          title="Back to cockpit"
        >
          <ArrowLeft size={15} />
        </button>
        <span
          className="font-display"
          style={{ color: 'var(--color-ink-3)', fontSize: 'var(--text-md)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>
        <div className="h-4 w-px" style={{ background: 'var(--color-divider)' }} />
        <span className="font-display" style={{ color: 'var(--color-ink)', fontSize: 'var(--text-md)' }}>
          Brief
        </span>
        <span
          className="mz-text-xs"
          style={{ color: 'var(--color-ink-4)', marginLeft: '12px' }}
          aria-live="polite"
        >
          {status === 'saving' ? 'Saving…'
            : status === 'saved' ? 'Saved'
            : status === 'error' ? 'Save failed'
            : ''}
        </span>
        <div className="ml-auto flex items-center gap-3">
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onSaveClick}
          >
            Save
          </button>
          <ThemeToggle />
        </div>
      </header>

      {/* Mock-data banner */}
      <div
        role="status"
        className="mz-text-xs"
        style={{
          padding: '6px 24px',
          background: 'var(--color-surface-2)',
          color: 'var(--color-ink-3)',
        }}
      >
        Showing placeholder data — backend save endpoint (BE-19) is not yet merged.
      </div>

      {/* Editor surface */}
      <main
        className="flex-1 overflow-y-auto"
        style={{ background: 'var(--color-surface)' }}
        aria-label="Brief editor"
      >
        <div
          className="mx-auto"
          style={{
            maxWidth: '760px',
            padding: '48px 32px',
          }}
        >
          <EditorContent
            editor={editor}
            className="font-display"
            style={{ color: 'var(--color-ink)' }}
          />
        </div>
      </main>
    </div>
  );
}

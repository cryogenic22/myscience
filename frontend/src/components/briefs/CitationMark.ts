import { Mark, mergeAttributes } from '@tiptap/core';

/**
 * PB-401 — citation mark. Wraps `{{cite:doc_id}}` tokens in the
 * editor doc so they render as inline chips. The mark stores the
 * `doc_id` as an HTML attribute (`data-citation`) so consumers
 * (and the regression test) can find it.
 *
 * Loop #15 ships the rendering side only — keyboard insertion is
 * handled by PB-402 (`AI suggestion → insert citation`).
 */

export interface CitationMarkOptions {
  HTMLAttributes: Record<string, unknown>;
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    citation: {
      setCitation: (docId: string) => ReturnType;
      unsetCitation: () => ReturnType;
    };
  }
}

export const CitationMark = Mark.create<CitationMarkOptions>({
  name: 'citation',
  inclusive: false,

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  addAttributes() {
    return {
      docId: {
        default: null,
        parseHTML: (el) => (el as HTMLElement).getAttribute('data-citation'),
        renderHTML: (attrs) =>
          attrs.docId ? { 'data-citation': attrs.docId as string } : {},
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-citation]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        class: 'mz-citation',
      }),
      0,
    ];
  },
});

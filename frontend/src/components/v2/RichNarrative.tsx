/**
 * RichNarrative — renders narrative text with inline entity mentions,
 * markdown bold, citation markers, and paragraph splitting.
 * Pure component: no API calls, only props in + callbacks out.
 */

import React from 'react';
import EntityMention from './EntityMention';

export interface EntityMentionData {
  entityId: string;
  entityType: string;
  name: string;
}

interface RichNarrativeProps {
  text: string;
  entityMentions?: EntityMentionData[];
  onEntityClick?: (entityId: string, entityType: string) => void;
}

/** LLM artifact tags to strip from output. */
const ARTIFACT_PATTERN = /\[(metrics|data|evidence|context)\]/gi;

/**
 * Build a case-insensitive regex that matches any entity name in the text.
 * Sorts by descending length so longest match wins when overlapping.
 */
function buildEntityRegex(mentions: EntityMentionData[]): RegExp | null {
  if (mentions.length === 0) return null;
  const sorted = [...mentions].sort((a, b) => b.name.length - a.name.length);
  const escaped = sorted.map((m) => m.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return new RegExp(`(${escaped.join('|')})`, 'gi');
}

/**
 * Build a lookup from lowercased entity name to its data.
 * If multiple mentions share a name (case-insensitive), the first wins.
 */
function buildNameMap(mentions: EntityMentionData[]): Map<string, EntityMentionData> {
  const map = new Map<string, EntityMentionData>();
  for (const m of mentions) {
    const key = m.name.toLowerCase();
    if (!map.has(key)) map.set(key, m);
  }
  return map;
}

/** Split text at entity-name boundaries and return React nodes. */
function renderWithEntities(
  text: string,
  mentions: EntityMentionData[],
  onEntityClick?: (entityId: string, entityType: string) => void,
): React.ReactNode[] {
  const regex = buildEntityRegex(mentions);
  if (!regex) return [text];

  const nameMap = buildNameMap(mentions);
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Reset regex state for repeated exec calls
  regex.lastIndex = 0;
  while ((match = regex.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index);
    if (before) parts.push(before);

    const matched = match[0];
    const data = nameMap.get(matched.toLowerCase());
    if (data) {
      parts.push(
        <EntityMention
          key={`entity-${match.index}`}
          name={matched}
          type={data.entityType}
          onClick={
            onEntityClick
              ? () => onEntityClick(data.entityId, data.entityType)
              : undefined
          }
        />,
      );
    } else {
      parts.push(matched);
    }
    lastIndex = match.index + matched.length;
  }

  const remaining = text.slice(lastIndex);
  if (remaining) parts.push(remaining);
  return parts;
}

/** Process inline formatting: bold and citations. */
function renderInlineFormatting(segment: string): React.ReactNode[] {
  // Combined pattern to split on bold and citations in one pass
  const combined = /(\*\*.+?\*\*|\[\d+\])/g;
  const nodes: React.ReactNode[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;

  combined.lastIndex = 0;
  while ((m = combined.exec(segment)) !== null) {
    const before = segment.slice(lastIdx, m.index);
    if (before) nodes.push(before);

    const token = m[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      // Bold
      nodes.push(
        <strong key={`bold-${m.index}`} style={{ fontWeight: 600 }}>
          {token.slice(2, -2)}
        </strong>,
      );
    } else {
      // Citation [N]
      const num = token.slice(1, -1);
      nodes.push(
        <sup
          key={`cite-${m.index}`}
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--accent)',
            cursor: 'pointer',
            fontWeight: 500,
            marginLeft: 1,
          }}
        >
          {num}
        </sup>,
      );
    }
    lastIdx = m.index + token.length;
  }

  const tail = segment.slice(lastIdx);
  if (tail) nodes.push(tail);
  return nodes;
}

/**
 * Full rendering pipeline: strip artifacts, split paragraphs,
 * highlight entity mentions, apply inline formatting.
 */
function renderParagraphs(
  text: string,
  mentions: EntityMentionData[] | undefined,
  onEntityClick?: (entityId: string, entityType: string) => void,
): React.ReactNode[] {
  // Strip LLM artifacts
  const cleaned = text.replace(ARTIFACT_PATTERN, '');

  // Split on double newlines for paragraphs
  const paragraphs = cleaned.split(/\n\n+/).filter((p) => p.trim());

  return paragraphs.map((para, pIdx) => {
    // Step 1: entity mentions
    const withEntities =
      mentions && mentions.length > 0
        ? renderWithEntities(para, mentions, onEntityClick)
        : [para];

    // Step 2: apply inline formatting to plain-string segments
    const fullyFormatted = withEntities.flatMap((node, nIdx) => {
      if (typeof node === 'string') {
        return renderInlineFormatting(node).map((formatted, fIdx) =>
          typeof formatted === 'string' ? (
            <React.Fragment key={`t-${pIdx}-${nIdx}-${fIdx}`}>{formatted}</React.Fragment>
          ) : (
            formatted
          ),
        );
      }
      return [node];
    });

    return (
      <p
        key={`p-${pIdx}`}
        style={{
          margin: 0,
          marginBottom: 'var(--space-3)',
        }}
      >
        {fullyFormatted}
      </p>
    );
  });
}

export default function RichNarrative({
  text,
  entityMentions,
  onEntityClick,
}: RichNarrativeProps) {
  return (
    <div
      style={{
        fontSize: 'var(--text-base)',
        color: 'var(--text-primary)',
        lineHeight: 1.6,
        fontFamily: 'var(--font-body)',
      }}
    >
      {renderParagraphs(text, entityMentions, onEntityClick)}
    </div>
  );
}

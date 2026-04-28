import type { Meta, StoryObj } from '@storybook/react';
import { CitationPill } from './CitationPill';

const meta: Meta<typeof CitationPill> = {
  title: 'Primitives/CitationPill',
  component: CitationPill,
  args: { source: 'edgar', ref: 0 },
};
export default meta;
type Story = StoryObj<typeof CitationPill>;

export const Default: Story = {};

export const Inline: Story = {
  render: () => (
    <p style={{ fontSize: 14, lineHeight: 1.7, maxWidth: 640 }}>
      Pfizer raised FY2026 revenue guidance by ~3% on the Q3 earnings call
      <CitationPill source="edgar" ref={0} title="8-K Item 2.02 — earnings press release" />
      , with the press release framing the change as &ldquo;narrowed to the upper half of prior range&rdquo;
      <CitationPill source="press" ref={1} title="Pfizer press release, 2026-04-25" />
      , corroborated by a Reuters wire
      <CitationPill source="news" ref={2} />
      . The move aligns with the Q1 commentary
      <CitationPill source="signal" ref="abc-123" title="Signal: Q1 guidance trajectory" />
      .
    </p>
  ),
};

export const SourceGallery: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {(['edgar','fda','ema','ct_gov','pubmed','pmc','dailymed','orange_book','patent','press','news','tier3','signal'] as const).map((s, i) => (
        <CitationPill key={s} source={s} ref={i} />
      ))}
    </div>
  ),
};

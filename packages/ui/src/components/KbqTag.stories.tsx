import type { Meta, StoryObj } from '@storybook/react';
import { KbqTag, type Kbq } from './KbqTag';

const meta: Meta<typeof KbqTag> = {
  title: 'Primitives/KbqTag',
  component: KbqTag,
  args: { kbq: 'clinical' },
};
export default meta;
type Story = StoryObj<typeof KbqTag>;

const ALL: Kbq[] = [
  'financial', 'governance', 'strategic', 'clinical', 'product',
  'ai_digital', 'conferences', 'pricing_access', 'regulatory', 'm_and_a', 'esg_supply',
];

export const Default: Story = {};

export const Full: Story = {
  render: () => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {ALL.map((k) => <KbqTag key={k} kbq={k} />)}
    </div>
  ),
};

export const Short: Story = {
  render: () => (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {ALL.map((k) => <KbqTag key={k} kbq={k} short />)}
    </div>
  ),
};

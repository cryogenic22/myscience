import type { Meta, StoryObj } from '@storybook/react';
import { ScoreTile } from './ScoreTile';

const meta: Meta<typeof ScoreTile> = {
  title: 'Primitives/ScoreTile',
  component: ScoreTile,
  args: {
    label: 'SIGNALS · 24H',
    value: 12,
    caption: 'across watchlist',
  },
};
export default meta;
type Story = StoryObj<typeof ScoreTile>;

export const Default: Story = {};

export const WithTrend: Story = {
  args: {
    label: 'HIGH IMPACT',
    value: 2,
    trend: 'up',
    trendValue: '+1',
    caption: 'vs yesterday',
  },
};

export const Dashboard: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <ScoreTile label="SIGNALS · 24H"   value={12} trend="up"   trendValue="+3" caption="across watchlist" />
      <ScoreTile label="HIGH IMPACT"     value={2}  trend="up"   trendValue="+1" caption="vs yesterday" />
      <ScoreTile label="REVIEWER QUEUE"  value={4}  trend="flat" trendValue="0"  caption="depth" />
      <ScoreTile label="LLM BUDGET"      value="$1,847" caption="of $5,000 this month" />
    </div>
  ),
};

export const Clickable: Story = {
  args: {
    label: 'OPEN DIGEST',
    value: 12,
    caption: 'click to triage',
    onClick: () => alert('opened digest'),
  },
};

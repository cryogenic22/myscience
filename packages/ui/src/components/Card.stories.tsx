import type { Meta, StoryObj } from '@storybook/react';
import { Card } from './Card';

const meta: Meta<typeof Card> = {
  title: 'Primitives/Card',
  component: Card,
  args: { variant: 'flat' },
  argTypes: {
    variant: { control: 'radio', options: ['flat', 'elevated', 'interactive'] },
  },
};
export default meta;

type Story = StoryObj<typeof Card>;

export const Flat: Story = {
  args: { variant: 'flat' },
  render: (args) => (
    <Card {...args} style={{ maxWidth: 360 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Pfizer · 8-K Item 5.02</div>
      <div style={{ color: 'var(--mz-color-text-secondary)', fontSize: 13 }}>
        CMO transition disclosed. Confirmed in filing + press release.
      </div>
    </Card>
  ),
};

export const Elevated: Story = {
  args: { variant: 'elevated' },
  render: (args) => (
    <Card {...args} style={{ maxWidth: 360 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>Score of the day</div>
      <div style={{ fontSize: 36, fontFamily: 'var(--mz-font-display)', letterSpacing: '-0.02em' }}>
        12<span style={{ color: 'var(--mz-color-text-tertiary)', fontSize: 18, marginLeft: 6 }}>signals</span>
      </div>
    </Card>
  ),
};

export const Interactive: Story = {
  args: { variant: 'interactive' },
  render: (args) => (
    <Card {...args} onClick={() => alert('opened')} style={{ maxWidth: 360 }}>
      <div style={{ fontWeight: 600 }}>Open Daily Digest →</div>
      <div style={{ color: 'var(--mz-color-text-secondary)', fontSize: 13, marginTop: 4 }}>
        12 new · 2 high-impact · 4 in queue
      </div>
    </Card>
  ),
};

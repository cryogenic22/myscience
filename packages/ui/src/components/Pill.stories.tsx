import type { Meta, StoryObj } from '@storybook/react';
import { Pill } from './Pill';

const meta: Meta<typeof Pill> = {
  title: 'Primitives/Pill',
  component: Pill,
  args: { tone: 'neutral', size: 'md', subtle: false, children: 'NEW' },
  argTypes: {
    tone: { control: 'select', options: ['neutral', 'accent', 'success', 'warning', 'danger', 'info'] },
    size: { control: 'radio', options: ['sm', 'md'] },
    subtle: { control: 'boolean' },
  },
};
export default meta;
type Story = StoryObj<typeof Pill>;

export const Default: Story = {};

export const TierGallery: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <Pill tone="success" subtle>CONFIRMED</Pill>
      <Pill tone="neutral" subtle>REPORTED</Pill>
      <Pill tone="warning" subtle>INFERRED</Pill>
      <Pill tone="danger"  subtle>DISPUTED</Pill>
    </div>
  ),
};

export const ImpactTiers: Story = {
  render: () => (
    <div style={{ display: 'flex', gap: 8 }}>
      <Pill tone="danger">HIGH</Pill>
      <Pill tone="warning">MEDIUM</Pill>
      <Pill tone="neutral">LOW</Pill>
    </div>
  ),
};

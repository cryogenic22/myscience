import type { Preview } from '@storybook/react';
import '@mz/design-tokens/tokens.css';
import '../src/styles.css';

const preview: Preview = {
  parameters: {
    backgrounds: {
      default: 'canvas-light',
      values: [
        { name: 'canvas-light',   value: '#FAFAF7' },
        { name: 'surface-light',  value: '#FFFFFF' },
        { name: 'canvas-dark',    value: '#0E0F11' },
        { name: 'surface-dark',   value: '#14161A' },
      ],
    },
    controls: {
      matchers: { color: /(background|color)$/i, date: /Date$/i },
    },
    a11y: { config: { rules: [] } },
    layout: 'padded',
  },
  globalTypes: {
    theme: {
      name: 'Theme',
      defaultValue: 'light',
      toolbar: {
        icon: 'paintbrush',
        items: [
          { value: 'light', title: 'Light' },
          { value: 'dark',  title: 'Dark' },
        ],
        showName: true,
      },
    },
    moduleAccent: {
      name: 'Module',
      defaultValue: 'ci',
      toolbar: {
        icon: 'circlehollow',
        items: [
          { value: 'ci',         title: 'CI (blue)' },
          { value: 'research',   title: 'Research (amber)' },
          { value: 'regulatory', title: 'Regulatory (teal)' },
        ],
        showName: true,
      },
    },
    density: {
      name: 'Density',
      defaultValue: 'comfortable',
      toolbar: {
        icon: 'component',
        items: ['compact', 'comfortable', 'spacious'],
        showName: true,
      },
    },
  },
  decorators: [
    (Story, ctx) => {
      const root = document.documentElement;
      root.setAttribute('data-theme',   ctx.globals.theme);
      root.setAttribute('data-module',  ctx.globals.moduleAccent);
      root.setAttribute('data-density', ctx.globals.density);
      return Story();
    },
  ],
};

export default preview;

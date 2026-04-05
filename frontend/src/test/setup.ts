import '@testing-library/jest-dom';

// Mock HTMLCanvasElement.getContext for KnowledgeGraph tests
HTMLCanvasElement.prototype.getContext = (() => {
  const noop = () => {};
  return {
    fillRect: noop,
    clearRect: noop,
    getImageData: () => ({ data: new Array(4) }),
    putImageData: noop,
    createImageData: () => [],
    setTransform: noop,
    drawImage: noop,
    save: noop,
    fillText: noop,
    restore: noop,
    beginPath: noop,
    moveTo: noop,
    lineTo: noop,
    closePath: noop,
    stroke: noop,
    translate: noop,
    scale: noop,
    rotate: noop,
    arc: noop,
    fill: noop,
    measureText: () => ({ width: 0, actualBoundingBoxAscent: 0, actualBoundingBoxDescent: 0 }),
    transform: noop,
    rect: noop,
    clip: noop,
    quadraticCurveTo: noop,
    bezierCurveTo: noop,
    createLinearGradient: () => ({ addColorStop: noop }),
    createRadialGradient: () => ({ addColorStop: noop }),
    createPattern: () => ({}),
    font: '',
    textAlign: 'start',
    textBaseline: 'alphabetic',
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    lineCap: 'butt',
    lineJoin: 'miter',
    globalAlpha: 1,
    globalCompositeOperation: 'source-over',
    setLineDash: noop,
    getLineDash: () => [],
    lineDashOffset: 0,
    shadowBlur: 0,
    shadowColor: '',
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    canvas: document.createElement('canvas'),
  };
}) as unknown as typeof HTMLCanvasElement.prototype.getContext;

// Mock import.meta.env for api module
Object.defineProperty(import.meta, 'env', {
  value: { DEV: true },
  writable: true,
});

// Mock ResizeObserver
globalThis.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Mock pointer capture
Element.prototype.setPointerCapture = () => {};
Element.prototype.releasePointerCapture = () => {};

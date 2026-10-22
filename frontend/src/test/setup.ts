import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

vi.mock('../mode', () => ({ apiMode: () => process.env.VITE_API_MODE }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

// jsdom has no native modal implementation; full keyboard/modal behavior is verified in Playwright.
Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) {
  this.open = true; this.querySelector<HTMLElement>('[autofocus]')?.focus();
} });

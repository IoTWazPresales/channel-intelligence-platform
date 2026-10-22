import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import React from 'react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
});

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = ResizeObserverMock;

// Numbers formatted without a locale follow the machine's: en-ZA prints "7 650" where the tests read "7,650".
// Pin en-US for calls that pass no locale, so the suite gives the same result on every machine.
const TEST_LOCALE = 'en-US';
const numberToLocaleString = Number.prototype.toLocaleString;
Number.prototype.toLocaleString = function (this: number, locales?: Intl.LocalesArgument, options?: Intl.NumberFormatOptions) {
  return numberToLocaleString.call(this, locales ?? TEST_LOCALE, options);
};
const RealNumberFormat = Intl.NumberFormat;
const PinnedNumberFormat = function (locales?: Intl.LocalesArgument, options?: Intl.NumberFormatOptions) {
  return new RealNumberFormat(locales ?? TEST_LOCALE, options);
} as unknown as typeof Intl.NumberFormat;
Object.defineProperty(PinnedNumberFormat, 'prototype', { value: RealNumberFormat.prototype });
PinnedNumberFormat.supportedLocalesOf = RealNumberFormat.supportedLocalesOf;
Intl.NumberFormat = PinnedNumberFormat;

vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) =>
    React.createElement('a', { href, ...rest }, children),
}));

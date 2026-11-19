import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ActionQueuePanel } from './ActionQueuePanel';
import type { ActionItem } from './actionQueue';

const items: ActionItem[] = [
  { key: 'awaiting-3', kind: 'awaiting_approval', caseId: 3, caseCode: 'CPR-3', label: 'CPR-3 · awaiting approval', hint: 'In Proposed.', tone: 'warning' },
  { key: 'claim-4', kind: 'claim_evidence_pending', caseId: 4, caseCode: 'CPR-4', label: 'CPR-4 · claim evidence pending', hint: 'Window ended.', tone: 'info' },
];

describe('ActionQueuePanel', () => {
  it('lists each waiting case and selects it on click', () => {
    const onSelect = vi.fn();
    renderWithProviders(<ActionQueuePanel items={items} onSelect={onSelect} />);
    expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-3 · awaiting approval');
    expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-4 · claim evidence pending');
    fireEvent.click(screen.getByText('CPR-4 · claim evidence pending'));
    expect(onSelect).toHaveBeenCalledWith(4);
  });
  it('says nothing is waiting when the queue is empty', () => {
    renderWithProviders(<ActionQueuePanel items={[]} onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-action-queue-empty')).toBeInTheDocument();
  });
  it('does not say nothing is waiting while a source is still loading', () => {
    renderWithProviders(<ActionQueuePanel items={[]} loading onSelect={vi.fn()} />);
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
    expect(screen.getByTestId('planner-action-queue-loading')).toBeInTheDocument();
  });
  it('shows an error instead of "nothing waiting" when a source failed, and names what is missing', () => {
    const onRetry = vi.fn();
    renderWithProviders(
      <ActionQueuePanel items={[]} unavailable={['Awaiting approval', 'Ended cases']} onRetry={onRetry} onSelect={vi.fn()} />,
    );
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
    const err = screen.getByTestId('planner-action-queue-error');
    expect(err).toHaveTextContent('Awaiting approval');
    expect(err).toHaveTextContent('Ended cases');
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalled();
  });
  it('keeps the rows it has and flags that the queue may be incomplete when a source failed', () => {
    renderWithProviders(<ActionQueuePanel items={items} unavailable={['Awaiting approval']} onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-4 · claim evidence pending');
    expect(screen.getByTestId('planner-action-queue-error')).toHaveTextContent(/incomplete/i);
  });
});

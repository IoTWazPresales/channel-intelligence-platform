import React from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { ActionQueuePanel, type QueueCard } from './ActionQueuePanel';
import type { ActionItem } from './actionQueue';

const items: ActionItem[] = [
  { key: 'awaiting-3', kind: 'awaiting_approval', caseId: 3, caseCode: 'CPR-3', label: 'CPR-3 · awaiting approval', hint: 'In Proposed.', tone: 'warning', overdue: false },
  { key: 'claim-4', kind: 'claim_evidence_pending', caseId: 4, caseCode: 'CPR-4', label: 'CPR-4 · claim evidence pending', hint: 'Window ended.', tone: 'info', overdue: false },
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
  it('does not say nothing is waiting when a source returned only its first page', () => {
    renderWithProviders(<ActionQueuePanel items={[]} incomplete onSelect={vi.fn()} />);
    expect(screen.queryByTestId('planner-action-queue-empty')).toBeNull();
    expect(screen.getByTestId('planner-action-queue-incomplete')).toBeInTheDocument();
  });
  it('keeps its rows and notes the partial view when a source has more pages', () => {
    renderWithProviders(<ActionQueuePanel items={items} incomplete onSelect={vi.fn()} />);
    expect(screen.getByTestId('planner-action-queue-partial')).toBeInTheDocument();
    expect(screen.getByTestId('planner-action-queue')).toHaveTextContent('CPR-3 · awaiting approval');
  });
  describe('queue cards', () => {
    const cards: QueueCard[] = [
      { key: 'overdue', label: 'Overdue approvals', value: 2, state: 'ready', caption: 'Window already started', tone: 'warning' },
      { key: 'evidence', label: 'Evidence outstanding', value: 0, state: 'ready' },
      { key: 'conflicts', label: 'Conflicting windows', value: null, state: 'empty', caption: 'Could not be loaded. Click to retry.' },
      { key: 'loading', label: 'Loading one', value: null, state: 'loading' },
    ];
    it('shows each card with its figure, and a card that did not load as a dash, never zero', () => {
      renderWithProviders(<ActionQueuePanel items={items} cards={cards} onSelect={vi.fn()} />);
      expect(screen.getByTestId('planner-queue-card-overdue')).toHaveTextContent('Overdue approvals2');
      expect(screen.getByTestId('planner-queue-card-evidence')).toHaveTextContent('Evidence outstanding0');
      const failed = screen.getByTestId('planner-queue-card-conflicts');
      expect(failed).toHaveTextContent('—');
      expect(failed).not.toHaveTextContent('0');
      expect(failed).toHaveAttribute('data-state', 'empty');
      expect(screen.getByTestId('planner-queue-card-loading')).toHaveAttribute('data-state', 'loading');
    });
    it('runs the card action on click', () => {
      const onClick = vi.fn();
      renderWithProviders(
        <ActionQueuePanel items={items} cards={[{ ...cards[0], onClick }]} onSelect={vi.fn()} />,
      );
      fireEvent.click(screen.getByTestId('planner-queue-card-overdue'));
      expect(onClick).toHaveBeenCalledTimes(1);
    });
    it('draws no card strip when there are no cards', () => {
      renderWithProviders(<ActionQueuePanel items={items} onSelect={vi.fn()} />);
      expect(screen.queryByTestId('planner-queue-cards')).toBeNull();
    });
  });
});

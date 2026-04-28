import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EntitySearchAutocomplete } from './EntitySearchAutocomplete';

type Row = { id: number; code: string };

describe('EntitySearchAutocomplete', () => {
  it('loads options from server search', async () => {
    const fetchOptions = vi.fn(async (q: string) => {
      if (!q.trim()) return [];
      return [{ id: 1, code: `match-${q}` }];
    });
    const user = userEvent.setup();
    render(
      <EntitySearchAutocomplete<Row>
        label="Test entity"
        value={null}
        onChange={() => undefined}
        fetchOptions={fetchOptions}
        getOptionLabel={(o) => o.code}
      />
    );
    const input = screen.getByLabelText('Test entity');
    await user.type(input, 'abc');
    await waitFor(() => expect(fetchOptions).toHaveBeenCalled());
    await waitFor(async () => {
      expect(await screen.findByText('match-abc')).toBeInTheDocument();
    });
  });
});

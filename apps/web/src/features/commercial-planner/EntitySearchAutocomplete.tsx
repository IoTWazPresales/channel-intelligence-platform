'use client';

import Autocomplete from '@mui/material/Autocomplete';
import CircularProgress from '@mui/material/CircularProgress';
import TextField from '@mui/material/TextField';
import { useCallback, useEffect, useState } from 'react';

export type EntitySearchAutocompleteProps<T extends { id: number }> = {
  label: string;
  value: T | null;
  onChange: (next: T | null) => void;
  fetchOptions: (q: string, signal: AbortSignal) => Promise<T[]>;
  getOptionLabel: (o: T) => string;
  disabled?: boolean;
  /** Shown under the field (e.g. operational hint for first-time users). */
  helperText?: string;
};

export function EntitySearchAutocomplete<T extends { id: number }>({
  label,
  value,
  onChange,
  fetchOptions,
  getOptionLabel,
  disabled,
  helperText,
}: EntitySearchAutocompleteProps<T>) {
  const [input, setInput] = useState('');
  const [debounced, setDebounced] = useState('');
  const [options, setOptions] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(input), 300);
    return () => clearTimeout(t);
  }, [input]);

  useEffect(() => {
    if (value) setInput(getOptionLabel(value));
    else setInput('');
  }, [value, getOptionLabel]);

  useEffect(() => {
    const ac = new AbortController();
    let cancelled = false;
    setLoading(true);
    void fetchOptions(debounced, ac.signal)
      .then((rows) => {
        if (!cancelled) setOptions(rows);
      })
      .catch(() => {
        if (!cancelled) setOptions([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [debounced, fetchOptions]);

  const onInputChange = useCallback((_: unknown, next: string, reason: string) => {
    if (reason === 'reset' && value) {
      setInput(getOptionLabel(value));
      return;
    }
    setInput(next);
  }, [value, getOptionLabel]);

  return (
    <Autocomplete<T, false, false, false>
      disabled={disabled}
      options={options}
      loading={loading}
      value={value}
      onChange={(_, v) => onChange(v)}
      inputValue={input}
      onInputChange={onInputChange}
      getOptionLabel={getOptionLabel}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      filterOptions={(x) => x}
      noOptionsText={debounced.trim() ? 'No matches' : 'Type to search'}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          helperText={helperText}
          InputProps={{
            ...params.InputProps,
            endAdornment: (
              <>
                {loading ? <CircularProgress color="inherit" size={18} /> : null}
                {params.InputProps.endAdornment}
              </>
            ),
          }}
        />
      )}
    />
  );
}

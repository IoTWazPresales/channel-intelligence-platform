import type { QueryKey } from '@tanstack/react-query';

/**
 * Contract for "mapping candidate list" domains (inbound evidence, distributor sell-in, etc.).
 * Naming stays domain-neutral so multiple import kinds can share hooks + workspace wiring later.
 */
export type MappingCandidatesListDomainConfig = {
  /** Stable id for logging / feature flags */
  readonly domainId: string;
  readonly candidatesQueryKey: (importJobId: number) => QueryKey;
  readonly candidatesUrl: (importJobId: number) => string;
  /** Optional: import job row for gating bulk actions (stage/status) */
  readonly importJobQueryKey: (importJobId: number) => QueryKey;
  readonly importJobUrl: (importJobId: number) => string;
  /** Status values excluded from the "open" steward list client-side */
  readonly terminalStatuses: ReadonlySet<string>;
};

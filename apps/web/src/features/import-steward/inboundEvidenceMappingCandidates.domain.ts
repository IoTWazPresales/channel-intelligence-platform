import type { ImportStewardListCopy } from './importStewardCandidateWorkspace.types';
import type { MappingCandidatesListDomainConfig } from './mappingCandidatesListDomain.types';

/**
 * List-domain configuration for **inbound shipment evidence** mapping candidates
 * (`/api/v1/shipment-evidence/import-jobs/{id}/mapping-candidates`).
 *
 * Query keys and paths match `ShipmentEntityStewardPanel` so future wiring stays drop-in compatible.
 */
export const inboundEvidenceMappingCandidatesListDomain = {
  domainId: 'inbound_evidence_mapping_candidates',
  candidatesQueryKey: (importJobId: number) => ['shipment-evidence-mapping-candidates', importJobId] as const,
  candidatesUrl: (importJobId: number) =>
    `/api/v1/shipment-evidence/import-jobs/${importJobId}/mapping-candidates`,
  importJobQueryKey: (importJobId: number) => ['import-job', importJobId] as const,
  importJobUrl: (importJobId: number) => `/api/v1/imports/jobs/${importJobId}`,
  terminalStatuses: new Set<string>(['resolved', 'ignored', 'waived_open_channel', 'steward_rejected']),
} as const satisfies MappingCandidatesListDomainConfig;

/** Default list shell copy (matches `ShipmentEntityStewardPanel` headings). */
export const inboundEvidenceMappingCandidatesListShellCopy: ImportStewardListCopy = {
  title: 'Shipment mapping candidates (import job)',
  description:
    'Distributor rows: unresolved Bill To / Ship To tokens. Channel partner rows: unresolved customer remarks tokens. Suggested actions are hints only; map and provisional apply create approved aliases and update evidence lines.',
};

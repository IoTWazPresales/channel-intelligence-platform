export type EvidenceBasis = 'claim_evidenced' | 'source_attested' | 'none';

export const EVIDENCE_BASIS_LABEL: Record<EvidenceBasis, string> = {
  claim_evidenced: 'Claim evidenced',
  source_attested: 'Source attested',
  none: 'No evidence',
};

export function isEvidenceBasis(value: string | null | undefined): value is EvidenceBasis {
  return value === 'claim_evidenced' || value === 'source_attested' || value === 'none';
}

export function evidenceBasisLabel(value: string | null | undefined): string {
  if (isEvidenceBasis(value)) return EVIDENCE_BASIS_LABEL[value];
  return '—';
}

import { describe, expect, it } from 'vitest';

import { planningLensFromPath, planningWorkflowHref } from './planningPaths';

describe('planningPaths', () => {
  it('maps production Planning routes onto hub and relocated leaves', () => {
    expect(planningLensFromPath('/lineup')).toBe('hub');
    expect(planningLensFromPath('/lineup/cases')).toBe('cases');
    expect(planningLensFromPath('/commercial-planner')).toBe('plans');
    expect(planningLensFromPath('/commercial-planner/cpor-cases')).toBe('hub');
    expect(planningLensFromPath('/roadmap')).toBe('roadmap');
  });

  it('relocates the N-0009 workspace href without changing other leaves', () => {
    expect(planningWorkflowHref('/lineup')).toBe('/lineup/cases');
    expect(planningWorkflowHref('/commercial-planner')).toBe('/commercial-planner');
    expect(planningWorkflowHref('/roadmap')).toBe('/roadmap');
  });
});

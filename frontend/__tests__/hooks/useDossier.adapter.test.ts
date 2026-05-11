import { describe, it, expect } from 'vitest';
import { adaptDossierResponse } from '../../src/hooks/useDossier';
import type { Dossier } from '../../src/types/dossier';

/**
 * BE-6 wire shape (see services/dossier.py compose_dossier):
 *   { entity: { id, type, name, aliases[], identity_fields },
 *     synthesis: { text_with_citation_marks, last_synthesised_at, owner_user_id } | null,
 *     recent_moves: [...],
 *     evidence_refs: [...],
 *     watching: [...],
 *     related_entities: [...] }
 */

describe('adaptDossierResponse — BE-6 wire shape → frontend Dossier', () => {
  it('maps entity.name → entity.canonical_name', () => {
    const wire = {
      entity: {
        id: 'ent-tirz',
        type: 'drug',
        name: 'tirzepatide',
        aliases: ['Mounjaro'],
        identity_fields: {},
      },
      synthesis: null,
      recent_moves: [],
      evidence_refs: [],
      watching: [],
      related_entities: [],
    };
    const out: Dossier = adaptDossierResponse(wire, 'tirzepatide');
    expect(out.entity.canonical_name).toBe('tirzepatide');
    expect(out.entity.type).toBe('drug');
    expect(out.entity.aliases).toEqual(['Mounjaro']);
  });

  it('passes slug from URL into entity.slug (BE does not return slug)', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: null, recent_moves: [], evidence_refs: [], watching: [], related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'my-slug');
    expect(out.entity.slug).toBe('my-slug');
  });

  it('partitions identity_fields into external IDs vs primary attributes', () => {
    const wire = {
      entity: {
        id: 'ent-1', type: 'drug', name: 'X', aliases: [],
        identity_fields: {
          rxnorm: '12345',
          chembl: 'CHEMBL1',
          ndc: '12345-0001',
          mechanism: 'GLP-1 agonist',
          approval_date: '2022-05-13',
          some_array_field: ['a', 'b'],   // dropped (non-scalar)
          nested_obj: { x: 1 },             // dropped (non-scalar)
        },
      },
      synthesis: null, recent_moves: [], evidence_refs: [], watching: [], related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'x');
    // External IDs detected by known key prefixes
    expect(out.entity.external_ids).toMatchObject({
      rxnorm: '12345',
      chembl: 'CHEMBL1',
      ndc: '12345-0001',
    });
    // Other scalar fields become primary attributes
    expect(out.entity.primary_attributes).toMatchObject({
      mechanism: 'GLP-1 agonist',
      approval_date: '2022-05-13',
    });
    // Non-scalar fields are dropped (would break the UI)
    expect(out.entity.primary_attributes).not.toHaveProperty('some_array_field');
    expect(out.entity.primary_attributes).not.toHaveProperty('nested_obj');
  });

  it('maps synthesis.text_with_citation_marks → synthesis.summary', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: {
        text_with_citation_marks: 'A summary with {{cite:doc1}} marker.',
        last_synthesised_at: '2026-05-01T00:00:00Z',
        owner_user_id: null,
      },
      recent_moves: [], evidence_refs: [], watching: [], related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'x');
    expect(out.synthesis?.summary).toContain('A summary');
    expect(out.synthesis?.citations).toEqual([]);
  });

  it('synthesis null in → synthesis null out (renders "Synthesis pending")', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: null,
      recent_moves: [], evidence_refs: [], watching: [], related_entities: [],
    };
    expect(adaptDossierResponse(wire, 'x').synthesis).toBeNull();
  });

  it('maps evidence_refs → evidence (renames evidence_id / source_tier → id / tier)', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: null,
      recent_moves: [],
      evidence_refs: [
        {
          evidence_id: 'ev-1',
          source_id: 'clinical_trials_gov',
          source_name: 'ClinicalTrials.gov',
          source_tier: 'T1',
          source_url: 'https://example.org',
          snippet: 'Phase 3 readout met primary endpoint.',
          published_at: '2026-04-15T00:00:00Z',
          confidence: 0.91,
        },
      ],
      watching: [], related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'x');
    expect(out.evidence).toHaveLength(1);
    expect(out.evidence[0]).toMatchObject({
      id: 'ev-1',
      source_name: 'ClinicalTrials.gov',
      tier: 'T1',
      snippet: 'Phase 3 readout met primary endpoint.',
    });
    expect(out.evidence[0].published_at).toBe('2026-04-15T00:00:00Z');
  });

  it('defaults source_tier to T3 when the backend returns null', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: null,
      recent_moves: [],
      evidence_refs: [
        { evidence_id: 'ev-1', source_name: '?', source_tier: null, snippet: '', published_at: null },
      ],
      watching: [], related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'x');
    expect(out.evidence[0].tier).toBe('T3');
  });

  it('maps watching → watchers and sets watcher_count', () => {
    const wire = {
      entity: { id: 'x', type: 'drug', name: 'X', aliases: [], identity_fields: {} },
      synthesis: null, recent_moves: [], evidence_refs: [],
      watching: [
        { user_id: 'u1', name: 'Maya', avatar_url: null },
        { user_id: 'u2', name: 'Ravi', avatar_url: 'https://x/avatar.png' },
      ],
      related_entities: [],
    };
    const out = adaptDossierResponse(wire, 'x');
    expect(out.watchers).toHaveLength(2);
    expect(out.watcher_count).toBe(2);
    expect(out.watchers[1].avatar_url).toBe('https://x/avatar.png');
  });
});

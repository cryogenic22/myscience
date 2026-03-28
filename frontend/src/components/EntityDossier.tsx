import { useState } from 'react';
import { ChevronDown, ChevronUp, CheckCircle, X, Edit3, MessageSquare, RefreshCw } from 'lucide-react';
import { api, type CatalogEntityDetail, type EntityLink } from '../api';
import { displayName, isUUID, QUALITY_CHECK_LABELS, SOURCE_LABELS, ENTITY_TYPE_LABELS } from '../brand';

/* ── Helpers ── */

function shortDate(v: string | null | undefined) {
  if (!v) return '—';
  return new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function str(v: unknown): string {
  if (v == null) return '';
  if (Array.isArray(v)) return v.join(', ');
  return String(v);
}

function display(v: unknown): string {
  if (v == null) return '—';
  if (Array.isArray(v)) return v.length > 0 ? v.join(', ') : '—';
  const s = String(v);
  if (!s) return '—';
  // Never show raw UUIDs to users
  if (isUUID(s)) return '—';
  return s;
}

const SKIP = new Set([
  '_label', 'content_hash', 'molecule_embedding', 'strategy_embedding',
  'protocol_embedding', 'abstract_embedding', 'scope_note_embedding',
  'label_embedding', 'full_text_embedding',
]);

/* ── Summary sentence generators ── */

function drugSummary(e: Record<string, unknown>): string {
  const name = str(e._label || e.generic_name || e.brand_name || e.name);
  const supply = str(e.supply_status);
  const authority = str(e.source_authority);

  const parts: string[] = [];
  parts.push(name || 'This drug');
  if (authority) parts.push(`is listed under ${SOURCE_LABELS[authority] ?? authority}`);
  if (supply) {
    const supplyLower = supply.toLowerCase();
    parts.push(parts.length > 1 ? `(${supplyLower})` : `has supply status: ${supplyLower}`);
  }
  if (e.approval_date) parts.push(`approved ${shortDate(str(e.approval_date))}`);
  return parts.join(' ') + '.';
}

function companySummary(e: Record<string, unknown>, links: EntityLink[]): string {
  const name = str(e._label || e.name);
  const drugCount = countLinksByType(links, 'drug', str(e.id));
  const trialCount = countLinksByType(links, 'trial', str(e.id));

  const parts: string[] = [];
  parts.push(name || 'This company');
  parts.push('is a pharmaceutical company');
  const metrics: string[] = [];
  if (drugCount > 0) metrics.push(`${drugCount} drug${drugCount !== 1 ? 's' : ''}`);
  if (trialCount > 0) metrics.push(`${trialCount} active trial${trialCount !== 1 ? 's' : ''}`);
  if (metrics.length > 0) parts.push(`with ${metrics.join(' and ')}`);
  return parts.join(' ') + '.';
}

function trialSummary(e: Record<string, unknown>): string {
  const title = str(e._label || e.official_title || e.name);
  const phase = str(e.phase);
  const status = str(e.status);
  const sponsor = str(e.sponsor_name);

  const parts: string[] = [];
  parts.push(title || 'This trial');
  const descriptors: string[] = [];
  if (phase) descriptors.push(phase);
  if (status) descriptors.push(status.toLowerCase());
  if (descriptors.length > 0) parts.push(`— a ${descriptors.join(' ')} trial`);
  if (sponsor) parts.push(`sponsored by ${sponsor}`);
  return parts.join(' ') + '.';
}

function genericSummary(e: Record<string, unknown>, entityType: string): string {
  const name = str(e._label || e.name || e.title);
  const typeLabel = entityType.replace(/_/g, ' ');
  return name ? `${name} (${typeLabel}).` : `A ${typeLabel} entity.`;
}

function generateSummary(entityType: string, entity: Record<string, unknown>, links: EntityLink[]): string {
  switch (entityType) {
    case 'drug': return drugSummary(entity);
    case 'company': return companySummary(entity, links);
    case 'trial': return trialSummary(entity);
    default: return genericSummary(entity, entityType);
  }
}

/* ── Connection counting ── */

function countLinksByType(links: EntityLink[], targetType: string, entityId: string): number {
  return links.filter(l => {
    const isSrc = l.source_entity_id === entityId;
    const relatedType = isSrc ? l.target_entity_type : l.source_entity_type;
    return relatedType === targetType;
  }).length;
}

function connectionSummary(links: EntityLink[], entityId: string): Array<{ type: string; count: number }> {
  const counts: Record<string, number> = {};
  for (const link of links) {
    const isSrc = link.source_entity_id === entityId;
    const relatedType = isSrc ? link.target_entity_type : link.source_entity_type;
    counts[relatedType] = (counts[relatedType] || 0) + 1;
  }
  return Object.entries(counts)
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count);
}

/* ── Section definitions by entity type ── */

interface FieldDef {
  key: string;
  label: string;
}

interface SectionDef {
  title: string;
  fields: FieldDef[];
}

function getDrugSections(): SectionDef[] {
  return [
    {
      title: 'Identity',
      fields: [
        { key: 'generic_name', label: 'Generic Name' },
        { key: 'brand_name', label: 'Brand Name' },
        { key: 'company_id', label: 'Company' },
        { key: 'mechanism_id', label: 'Mechanism' },
        { key: 'therapeutic_area_id', label: 'Therapeutic Area' },
        { key: 'source_authority', label: 'Authority' },
      ],
    },
    {
      title: 'Pipeline',
      fields: [
        { key: 'phase', label: 'Phase' },
        { key: 'approval_date', label: 'Approval Date' },
        { key: 'patent_expiry_date', label: 'Patent Expiry' },
        { key: 'supply_status', label: 'Supply Status' },
        { key: 'record_status', label: 'Record Status' },
      ],
    },
  ];
}

function getCompanySections(): SectionDef[] {
  return [
    {
      title: 'Identity',
      fields: [
        { key: 'name', label: 'Name' },
        { key: 'ticker', label: 'Ticker' },
        { key: 'cik', label: 'CIK' },
        { key: 'region', label: 'Region' },
        { key: 'country', label: 'Country' },
        { key: 'sic_code', label: 'SIC Code' },
      ],
    },
    {
      title: 'Portfolio',
      fields: [
        { key: 'market_cap_tier', label: 'Market Cap Tier' },
      ],
    },
  ];
}

function getTrialSections(): SectionDef[] {
  return [
    {
      title: 'Identity',
      fields: [
        { key: 'id', label: 'NCT ID' },
        { key: 'official_title', label: 'Title' },
        { key: 'phase', label: 'Phase' },
        { key: 'status', label: 'Status' },
        { key: 'sponsor_name', label: 'Sponsor' },
      ],
    },
    {
      title: 'Design',
      fields: [
        { key: 'enrollment_target', label: 'Enrollment Target' },
        { key: 'start_date', label: 'Start Date' },
        { key: 'primary_completion_date', label: 'Primary Completion' },
        { key: 'study_type', label: 'Study Type' },
        { key: 'conditions', label: 'Conditions' },
        { key: 'drug_id', label: 'Drug' },
      ],
    },
  ];
}

function getSections(entityType: string): SectionDef[] {
  switch (entityType) {
    case 'drug': return getDrugSections();
    case 'company': return getCompanySections();
    case 'trial': return getTrialSections();
    default: return [];
  }
}

/* ── Phase badge ── */

function PhaseBadge({ phase }: { phase: string }) {
  const p = phase.toLowerCase();
  let color = 'var(--color-ink-4)';
  let bg = 'var(--color-surface-2)';
  if (p.includes('4') || p.includes('approved') || p.includes('market')) {
    color = 'var(--color-green)'; bg = 'color-mix(in srgb, var(--color-green) 12%, transparent)';
  } else if (p.includes('3')) {
    color = '#2563eb'; bg = 'color-mix(in srgb, #2563eb 12%, transparent)';
  } else if (p.includes('2')) {
    color = 'var(--color-amber)'; bg = 'color-mix(in srgb, var(--color-amber) 12%, transparent)';
  } else if (p.includes('1')) {
    color = 'var(--color-ink-3)'; bg = 'var(--color-surface-2)';
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      fontSize: '11px', fontWeight: 600,
      color, background: bg,
      padding: '2px 10px', borderRadius: '12px',
      letterSpacing: '0.02em',
    }}>
      {phase}
    </span>
  );
}

/* ── Section renderer ── */

function StructuredSection({ title, fields, entity, editable, editing, onEditField }: {
  title: string;
  fields: FieldDef[];
  entity: Record<string, unknown>;
  editable: Set<string>;
  editing: Record<string, string>;
  onEditField: (f: string, v: string) => void;
}) {
  // Only show fields that exist and have values
  const visible = fields.filter(f => {
    const val = entity[f.key];
    return val != null && val !== '' && val !== 'null';
  });

  // Deduplicate: if two fields map to same label, keep the first with a value
  const seen = new Set<string>();
  const deduped = visible.filter(f => {
    if (seen.has(f.label)) return false;
    seen.add(f.label);
    return true;
  });

  if (deduped.length === 0) return null;

  return (
    <div style={{ marginBottom: '20px' }}>
      <div style={{
        fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
        letterSpacing: '0.06em', color: 'var(--color-ink-4)',
        marginBottom: '10px',
      }}>
        {title}
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(100px, 35%) 1fr',
        gap: '2px 12px',
      }}>
        {deduped.map(f => {
          const val = entity[f.key];
          const isEditing = f.key in editing;
          const isPhase = (f.key === 'phase' && val);

          return (
            <div
              key={f.key}
              style={{
                display: 'contents',
              }}
            >
              <span style={{
                paddingTop: '7px',
                fontSize: '12px', color: 'var(--color-ink-4)',
              }}>
                {f.label}
              </span>
              {isEditing ? (
                <input
                  value={editing[f.key]}
                  onChange={e => onEditField(f.key, e.target.value)}
                  className="input-base"
                  style={{ flex: 1, padding: '3px 8px', fontSize: '12px', borderRadius: '6px' }}
                  autoFocus
                />
              ) : isPhase ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 0' }}>
                  <PhaseBadge phase={String(val)} />
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', padding: '5px 0' }}>
                  <span style={{
                    fontSize: '12px', color: 'var(--color-ink-2)',
                    flex: 1, wordBreak: 'break-word',
                  }}>
                    {(() => {
                      const raw = display(val);
                      if (raw === '—') return f.key.endsWith('_id') ? 'Not linked' : '—';
                      if (f.key === 'source_authority' || f.key === 'source_api') return SOURCE_LABELS[raw] ?? raw;
                      if (f.key === 'supply_status' || f.key === 'record_status' || f.key === 'marketing_status')
                        return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase();
                      return raw;
                    })()}
                  </span>
                  {editable.has(f.key) && !isEditing && (
                    <button
                      type="button"
                      onClick={() => onEditField(f.key, String(val ?? ''))}
                      style={{
                        flexShrink: 0, color: 'var(--color-ink-4)',
                        background: 'none', border: 'none', cursor: 'pointer',
                        padding: '2px', opacity: 0, transition: 'opacity 150ms',
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '0'; }}
                    >
                      <Edit3 size={11} />
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Main component ── */

interface EntityDossierProps {
  detail: CatalogEntityDetail;
  editing: Record<string, string>;
  onEditField: (f: string, v: string) => void;
  onSave: () => Promise<void>;
  onAskInChat?: (q: string) => void;
  onNavigateEntity?: (entityType: string, entityId: string) => void;
}

export default function EntityDossier({ detail, editing, onEditField, onSave, onAskInChat, onNavigateEntity }: EntityDossierProps) {
  const entity = detail.entity;
  const entityType = detail.entity_type;
  const editable = new Set(detail.editable_fields);
  const hasEdits = Object.keys(editing).length > 0;
  const [saving, setSaving] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const [expandedConnection, setExpandedConnection] = useState<string | null>(null);

  const entityId = String(entity.id ?? '');
  const sections = getSections(entityType);
  const summary = generateSummary(entityType, entity, detail.links);
  const connections = connectionSummary(detail.links, entityId);

  // Collect all keys used in structured sections so we can exclude them from technical details
  const structuredKeys = new Set<string>();
  for (const sec of sections) {
    for (const f of sec.fields) {
      if (entity[f.key] != null && entity[f.key] !== '') {
        structuredKeys.add(f.key);
      }
    }
  }

  const save = async () => {
    setSaving(true);
    try { await onSave(); } finally { setSaving(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Summary sentence */}
      <div style={{
        fontSize: '13px', lineHeight: 1.6,
        color: 'var(--color-ink-2)',
        padding: '12px 14px',
        background: 'var(--color-surface-2)',
        borderRadius: '10px',
        borderLeft: '3px solid var(--color-accent)',
      }}>
        {summary}
      </div>

      {/* Trust & confidence card */}
      {detail.quality_results.length > 0 && (() => {
        const passed = detail.quality_results.filter(q => q.passed).length;
        const total = detail.quality_results.length;
        const pct = Math.round((passed / total) * 100);
        const trustLevel = pct >= 80 ? 'Certified' : pct >= 50 ? 'Partial' : 'Incomplete';
        const trustColor = pct >= 80 ? 'var(--color-green)' : pct >= 50 ? 'var(--color-amber)' : 'var(--color-ink-4)';
        const trustBg = pct >= 80 ? 'var(--color-green-soft)' : pct >= 50 ? 'var(--color-amber-soft)' : 'var(--color-surface-2)';
        const sourceCount = new Set(detail.links.map(l => l.provenance_source).filter(Boolean)).size;
        const linkCount = detail.links.length;

        return (
          <div style={{
            display: 'flex', gap: '12px', flexWrap: 'wrap',
          }}>
            <div style={{
              flex: 1, minWidth: '140px',
              padding: '10px 14px', borderRadius: '10px',
              background: trustBg, border: `1px solid color-mix(in srgb, ${trustColor} 20%, transparent)`,
            }}>
              <div style={{ fontSize: '20px', fontWeight: 700, color: trustColor }}>{pct}%</div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: trustColor }}>{trustLevel}</div>
              <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px' }}>{passed}/{total} checks passed</div>
            </div>
            <div style={{
              flex: 1, minWidth: '140px',
              padding: '10px 14px', borderRadius: '10px',
              background: 'var(--color-surface-2)',
            }}>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-ink)' }}>{linkCount}</div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-ink-3)' }}>Connections</div>
              <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px' }}>{sourceCount} data source{sourceCount !== 1 ? 's' : ''}</div>
            </div>
          </div>
        );
      })()}

      {/* Structured sections */}
      {sections.length > 0 && (
        <div>
          {sections.map(sec => (
            <StructuredSection
              key={sec.title}
              title={sec.title}
              fields={sec.fields}
              entity={entity}
              editable={editable}
              editing={editing}
              onEditField={onEditField}
            />
          ))}
        </div>
      )}

      {/* Connections summary */}
      {connections.length > 0 && (
        <section>
          <div style={{
            fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.06em', color: 'var(--color-ink-4)',
            marginBottom: '10px',
          }}>
            Connections ({detail.links.length})
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {connections.map(c => (
              <button
                key={c.type}
                onClick={() => setExpandedConnection(expandedConnection === c.type ? null : c.type)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: '6px',
                  fontSize: '12px', fontWeight: 500,
                  color: expandedConnection === c.type ? 'var(--color-accent)' : 'var(--color-ink-2)',
                  background: expandedConnection === c.type ? 'var(--color-accent-soft)' : 'var(--color-surface-2)',
                  padding: '4px 12px', borderRadius: '16px',
                  border: `1px solid ${expandedConnection === c.type ? 'var(--color-accent)' : 'var(--color-line)'}`,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{ fontWeight: 600, color: expandedConnection === c.type ? 'var(--color-accent)' : 'var(--color-ink)' }}>{c.count}</span>
                <span>{ENTITY_TYPE_LABELS[c.type] ?? c.type.replace(/_/g, ' ')}{c.count !== 1 ? 's' : ''}</span>
              </button>
            ))}
          </div>

          {/* Expanded connection: show linked entity names */}
          {expandedConnection && (() => {
            const linked = detail.links.filter(l => {
              const isSource = l.source_entity_id === entityId;
              const otherType = isSource ? l.target_entity_type : l.source_entity_type;
              return otherType === expandedConnection;
            });
            // Deduplicate by entity ID
            const seen = new Set<string>();
            const unique = linked.filter(l => {
              const otherId = l.source_entity_id === entityId ? l.target_entity_id : l.source_entity_id;
              if (seen.has(otherId)) return false;
              seen.add(otherId);
              return true;
            });
            return (
              <div style={{
                marginTop: '8px', padding: '10px 12px',
                background: 'var(--color-surface-2)', borderRadius: '8px',
                maxHeight: '200px', overflowY: 'auto',
              }}>
                <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginBottom: '6px', fontWeight: 600 }}>
                  {ENTITY_TYPE_LABELS[expandedConnection] ?? expandedConnection} ({unique.length})
                </div>
                {unique.slice(0, 50).map(l => {
                  const otherId = l.source_entity_id === entityId ? l.target_entity_id : l.source_entity_id;
                  const otherType = l.source_entity_id === entityId ? l.target_entity_type : l.source_entity_type;
                  const isSource = l.source_entity_id === entityId;
                  const label = isSource
                    ? (l.target_label ?? otherId)
                    : (l.source_label ?? otherId);
                  return (
                    <div
                      key={otherId + l.link_type}
                      onClick={() => onNavigateEntity?.(otherType, otherId)}
                      style={{
                        fontSize: '12px', padding: '4px 0',
                        color: 'var(--color-ink-2)',
                        cursor: onNavigateEntity ? 'pointer' : 'default',
                        borderBottom: '1px solid var(--color-line)',
                      }}
                    >
                      <span style={{ fontWeight: 500, color: 'var(--color-ink)' }}>
                        {String(label)}
                      </span>
                      <span style={{ marginLeft: '8px', fontSize: '10px', color: 'var(--color-ink-4)' }}>
                        {l.link_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                  );
                })}
                {unique.length > 50 && (
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', paddingTop: '6px' }}>
                    + {unique.length - 50} more
                  </div>
                )}
              </div>
            );
          })()}
        </section>
      )}

      {/* Save bar for edits */}
      {hasEdits && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingTop: '12px', borderTop: '1px solid var(--color-line)' }}>
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="btn btn-accent btn-sm"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      )}

      {/* Quality — collapsed into a single confidence badge with expandable details */}
      {detail.quality_results.length > 0 && (() => {
        const passed = detail.quality_results.filter(q => q.passed).length;
        const total = detail.quality_results.length;
        const pct = Math.round((passed / total) * 100);
        const color = pct >= 80 ? 'var(--color-green)' : pct >= 50 ? 'var(--color-amber)' : 'var(--color-red)';
        const failed = detail.quality_results.filter(q => !q.passed);

        return (
          <section>
            <div style={{
              fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
              letterSpacing: '0.06em', color: 'var(--color-ink-4)',
              marginBottom: '10px',
            }}>
              Data Quality
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '12px',
              padding: '10px 14px', borderRadius: '10px',
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-line)',
            }}>
              <div style={{
                width: '36px', height: '36px', borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '13px', fontWeight: 700, color: 'white',
                background: color,
              }}>
                {pct}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink)' }}>
                  {passed}/{total} checks passed
                </div>
                {failed.length > 0 && (
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-3)', marginTop: '2px' }}>
                    Missing: {failed.map(q => QUALITY_CHECK_LABELS[q.rule_name] ?? displayName(q.rule_name)).join(', ')}
                  </div>
                )}
              </div>
            </div>
          </section>
        );
      })()}

      {/* Data provenance */}
      {(entity.source_api || entity.retrieved_at) && (
        <section>
          <div style={{
            fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.06em', color: 'var(--color-ink-4)',
            marginBottom: '10px',
          }}>
            Data Provenance
          </div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(80px, 35%) 1fr',
            gap: '4px 12px',
            fontSize: '12px',
          }}>
            {entity.source_api && (
              <>
                <span style={{ color: 'var(--color-ink-4)' }}>Source</span>
                <span style={{ color: 'var(--color-ink-2)' }}>{SOURCE_LABELS[String(entity.source_api)] ?? String(entity.source_api)}</span>
              </>
            )}
            {entity.retrieved_at && (
              <>
                <span style={{ color: 'var(--color-ink-4)' }}>Retrieved</span>
                <span style={{ color: 'var(--color-ink-2)' }}>{shortDate(String(entity.retrieved_at))}</span>
              </>
            )}
          </div>
        </section>
      )}

      {/* Change history */}
      {detail.change_log.length > 0 && (
        <section>
          <div style={{
            fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.06em', color: 'var(--color-ink-4)',
            marginBottom: '10px',
          }}>
            Change History
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {detail.change_log.slice(0, 10).map((ch, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '11px' }}>
                <div style={{
                  flexShrink: 0, height: '8px', width: '8px', borderRadius: '50%', marginTop: '4px',
                  background: ch.change_type === 'manual_edit' ? 'var(--color-accent)' : 'var(--color-ink-4)',
                }} />
                <div>
                  <span style={{ color: 'var(--color-ink-2)' }}>{displayName(ch.change_type)}</span>
                  {ch.changed_fields?.length > 0 && (
                    <span style={{ color: 'var(--color-ink-4)' }}> · {ch.changed_fields.map((f: string) => displayName(f)).join(', ')}</span>
                  )}
                  <div style={{ color: 'var(--color-ink-4)' }}>{shortDate(ch.changed_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Technical details (collapsed) */}
      <section>
        <button
          type="button"
          onClick={() => setTechOpen(prev => !prev)}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            fontSize: '11px', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '0.06em', color: 'var(--color-ink-4)',
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '0', marginBottom: techOpen ? '10px' : '0',
          }}
        >
          {techOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          Technical Details
        </button>
        {techOpen && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(100px, 35%) 1fr',
            gap: '2px 12px',
          }}>
            {Object.entries(entity)
              .filter(([k]) => !SKIP.has(k))
              .map(([key, val]) => {
                const isEditing = key in editing;
                return (
                  <div
                    key={key}
                    style={{ display: 'contents' }}
                  >
                    <span style={{
                      paddingTop: '7px',
                      fontSize: '12px', color: 'var(--color-ink-4)',
                    }}>
                      {displayName(key)}
                    </span>
                    {isEditing ? (
                      <input
                        value={editing[key]}
                        onChange={e => onEditField(key, e.target.value)}
                        className="input-base"
                        style={{ flex: 1, padding: '3px 8px', fontSize: '12px', borderRadius: '6px' }}
                        autoFocus
                      />
                    ) : (
                      <span style={{
                        fontSize: '12px', color: 'var(--color-ink-2)',
                        flex: 1, wordBreak: 'break-word',
                      }}>
                        {display(val)}
                      </span>
                    )}
                    {editable.has(key) && !isEditing && (
                      <button
                        type="button"
                        onClick={() => onEditField(key, String(val ?? ''))}
                        style={{
                          flexShrink: 0, color: 'var(--color-ink-4)',
                          background: 'none', border: 'none', cursor: 'pointer',
                          padding: '2px', opacity: 0, transition: 'opacity 150ms',
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '0'; }}
                      >
                        <Edit3 size={11} />
                      </button>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </section>

      {/* Actions */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', paddingTop: '16px', borderTop: '1px solid var(--color-line)' }}>
        {onAskInChat && (
          <button
            type="button"
            onClick={() => {
              const label = String(entity._label ?? entity.generic_name ?? entity.name ?? '');
              onAskInChat(`Tell me about ${label}`);
            }}
            className="btn btn-secondary btn-sm"
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <MessageSquare size={13} />
            Explore in Chat
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            api.catalogRunEnrichment(entityType, 1).catch(() => {});
          }}
          className="btn btn-secondary btn-sm"
          style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
        >
          <RefreshCw size={13} />
          Request AI Enrichment
        </button>
      </div>
    </div>
  );
}

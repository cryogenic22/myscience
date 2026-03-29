import React, { useState } from 'react';
import '../newui.css';
import EntityDot from '../components/v2/EntityDot';
import EntityCard from '../components/v2/EntityCard';
import EntityMention from '../components/v2/EntityMention';
import ConfidenceBar from '../components/v2/ConfidenceBar';
import Button from '../components/v2/Button';
import Input from '../components/v2/Input';
import Panel from '../components/v2/Panel';
import Badge from '../components/v2/Badge';

const SECTION_STYLE: React.CSSProperties = {
  marginBottom: 'var(--space-8)',
};

const SECTION_TITLE: React.CSSProperties = {
  fontFamily: 'var(--font-display)',
  fontSize: 'var(--text-xl)',
  color: 'var(--text-primary)',
  marginBottom: 'var(--space-4)',
  fontWeight: 600,
};

const SUBSECTION: React.CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--text-sm)',
  color: 'var(--text-secondary)',
  marginBottom: 'var(--space-2)',
  fontWeight: 500,
};

export default function NewWorkspace() {
  const [searchValue, setSearchValue] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  return (
    <div
      style={{
        padding: 'var(--space-8)',
        background: 'var(--surface-primary)',
        minHeight: '100vh',
        fontFamily: 'var(--font-body)',
      }}
    >
      <h1
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'var(--text-3xl)',
          color: 'var(--text-primary)',
          marginBottom: 'var(--space-2)',
        }}
      >
        Market Zero — Design System
      </h1>
      <p
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-base)',
          color: 'var(--text-secondary)',
          marginBottom: 'var(--space-8)',
        }}
      >
        SPEC-009 Phase 0 — Component gallery. All tokens from newui.css. No Tailwind. No magic numbers.
      </p>

      {/* ── Entity Dots ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Entity Dots</h2>
        <div style={{ display: 'flex', gap: 'var(--space-4)', alignItems: 'center', flexWrap: 'wrap' }}>
          {['drug', 'company', 'trial', 'mechanism', 'literature', 'target', 'therapeutic_area', 'safety'].map((t) => (
            <div key={t} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
              <EntityDot type={t} size="sm" />
              <EntityDot type={t} size="md" />
              <EntityDot type={t} size="lg" />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{t}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Confidence Bars ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Confidence Bars</h2>
        <div style={{ maxWidth: 360, display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <div>
            <span style={SUBSECTION}>High (92%)</span>
            <ConfidenceBar value={0.92} showLabel />
          </div>
          <div>
            <span style={SUBSECTION}>Medium (55%)</span>
            <ConfidenceBar value={0.55} showLabel />
          </div>
          <div>
            <span style={SUBSECTION}>Low (18%)</span>
            <ConfidenceBar value={0.18} showLabel />
          </div>
        </div>
      </section>

      {/* ── Entity Mentions ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Entity Mentions (inline)</h2>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--text-base)', color: 'var(--text-primary)', lineHeight: 1.7 }}>
          The drug <EntityMention name="Semaglutide" type="drug" onClick={() => {}} /> manufactured by{' '}
          <EntityMention name="Novo Nordisk" type="company" onClick={() => {}} /> targets the{' '}
          <EntityMention name="GLP-1 receptor" type="mechanism" onClick={() => {}} /> and has been studied in{' '}
          <EntityMention name="NCT04567890" type="trial" onClick={() => {}} />.
        </p>
      </section>

      {/* ── Entity Cards ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Entity Cards</h2>

        <div style={SUBSECTION}>Compact</div>
        <div style={{ marginBottom: 'var(--space-4)' }}>
          <EntityCard name="Semaglutide" type="drug" descriptor="GLP-1 receptor agonist" variant="compact" />
        </div>

        <div style={SUBSECTION}>Standard</div>
        <div style={{ maxWidth: 400, marginBottom: 'var(--space-4)' }}>
          <EntityCard
            name="Semaglutide"
            type="drug"
            descriptor="GLP-1 receptor agonist"
            metadata="Novo Nordisk \u00b7 Approved \u00b7 T2D"
            confidence={0.92}
            connections={{ trial: 47, mechanism: 12, literature: 156 }}
            variant="standard"
          />
        </div>

        <div style={SUBSECTION}>Expanded</div>
        <div style={{ maxWidth: 400 }}>
          <EntityCard
            name="Semaglutide"
            type="drug"
            descriptor="GLP-1 receptor agonist"
            metadata="Novo Nordisk \u00b7 Approved \u00b7 T2D"
            confidence={0.92}
            connections={{ trial: 47, mechanism: 12, literature: 156 }}
            variant="expanded"
          />
        </div>
      </section>

      {/* ── Badges ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Badges</h2>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <Badge label="Default" />
          <Badge label="Phase III" variant="info" />
          <Badge label="Approved" variant="success" />
          <Badge label="Under Review" variant="warning" />
          <Badge label="Discontinued" variant="error" />
          <Badge label="Medium Badge" variant="info" size="md" />
        </div>
      </section>

      {/* ── Buttons ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Buttons</h2>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <Button variant="primary">Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="primary" size="sm">Small Primary</Button>
          <Button variant="secondary" size="sm">Small Secondary</Button>
          <Button variant="primary" disabled>Disabled</Button>
          <Button variant="secondary" disabled>Disabled</Button>
        </div>
      </section>

      {/* ── Inputs ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Inputs</h2>
        <div style={{ maxWidth: 400, display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <div>
            <div style={SUBSECTION}>Search variant</div>
            <Input
              variant="search"
              placeholder="Search entities..."
              value={searchValue}
              onChange={setSearchValue}
            />
          </div>
          <div>
            <div style={SUBSECTION}>Default variant</div>
            <Input
              variant="default"
              placeholder="Type something..."
              value={inputValue}
              onChange={setInputValue}
            />
          </div>
        </div>
      </section>

      {/* ── Panels ── */}
      <section style={SECTION_STYLE}>
        <h2 style={SECTION_TITLE}>Panels (collapsible)</h2>
        <div
          style={{
            display: 'flex',
            height: 200,
            border: '1px solid var(--surface-secondary)',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
          }}
        >
          <Panel side="left" width={200} collapsed={leftCollapsed} onToggle={() => setLeftCollapsed(!leftCollapsed)}>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
              <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Left Panel</div>
              <div style={{ color: 'var(--text-secondary)' }}>Dialogue / chat area</div>
            </div>
          </Panel>
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-tertiary)',
              backgroundColor: 'var(--surface-secondary)',
            }}
          >
            Main content area
          </div>
          <Panel side="right" width={200} collapsed={rightCollapsed} onToggle={() => setRightCollapsed(!rightCollapsed)}>
            <div style={{ fontFamily: 'var(--font-body)', fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
              <div style={{ fontWeight: 600, marginBottom: 'var(--space-2)' }}>Right Panel</div>
              <div style={{ color: 'var(--text-secondary)' }}>Inspector / details</div>
            </div>
          </Panel>
        </div>
      </section>
    </div>
  );
}

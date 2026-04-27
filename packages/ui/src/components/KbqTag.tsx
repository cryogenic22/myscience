import { Pill } from './Pill';

/** The 11 Key Business Questions from the CI design. */
export type Kbq =
  | 'financial'
  | 'governance'
  | 'strategic'
  | 'clinical'
  | 'product'
  | 'ai_digital'
  | 'conferences'
  | 'pricing_access'
  | 'regulatory'
  | 'm_and_a'
  | 'esg_supply';

const KBQ_LABEL: Record<Kbq, string> = {
  financial:      'KBQ1 · Financial',
  governance:     'KBQ2 · Exec',
  strategic:      'KBQ3 · Strategy',
  clinical:       'KBQ4 · Clinical',
  product:        'KBQ5 · Product',
  ai_digital:     'KBQ6 · AI',
  conferences:    'KBQ7 · Conferences',
  pricing_access: 'KBQ8 · Pricing',
  regulatory:     'KBQ9 · Regulatory',
  m_and_a:        'KBQ10 · M&A',
  esg_supply:     'KBQ11 · ESG',
};

const KBQ_SHORT: Record<Kbq, string> = {
  financial: 'FIN', governance: 'EXEC', strategic: 'STRAT', clinical: 'CLIN',
  product: 'PROD', ai_digital: 'AI', conferences: 'CONF', pricing_access: 'PRICE',
  regulatory: 'REG', m_and_a: 'M&A', esg_supply: 'ESG',
};

export interface KbqTagProps {
  kbq: Kbq;
  short?: boolean;
}

/**
 * KbqTag — visual marker for a Signal's KBQ membership.
 * Used on signal cards and in filter chips.
 */
export function KbqTag({ kbq, short = false }: KbqTagProps) {
  return (
    <Pill tone="accent" subtle size="sm" title={KBQ_LABEL[kbq]}>
      {short ? KBQ_SHORT[kbq] : KBQ_LABEL[kbq]}
    </Pill>
  );
}

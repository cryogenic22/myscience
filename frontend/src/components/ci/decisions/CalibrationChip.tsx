import { Activity } from 'lucide-react';

interface Props {
  score: number | null;
}

/** Chip showing the calibration score (predicted vs actual quality).
 *  >0.66 green, >0.33 amber, else red. Null hides the chip entirely. */
export default function CalibrationChip({ score }: Props) {
  if (score === null || score === undefined) return null;

  let bg = '#FEE2E2';
  let fg = '#B91C1C';
  let label = 'low';
  if (score >= 0.66) {
    bg = '#DCFCE7';
    fg = '#15803D';
    label = 'well calibrated';
  } else if (score >= 0.33) {
    bg = '#FEF3C7';
    fg = '#A16207';
    label = 'mid calibrated';
  } else {
    label = 'miscalibrated';
  }

  return (
    <span
      className="text-[10px] inline-flex items-center gap-1 font-medium"
      style={{
        padding: '2px 7px',
        borderRadius: '4px',
        background: bg,
        color: fg,
      }}
      title={`Calibration ${(score * 100).toFixed(0)}% — predicted vs actual quality. >66% well calibrated, >33% mid, else miscalibrated.`}
    >
      <Activity size={10} />
      Cal {(score * 100).toFixed(0)}%
      <span style={{ opacity: 0.7, marginLeft: '2px' }}>· {label}</span>
    </span>
  );
}

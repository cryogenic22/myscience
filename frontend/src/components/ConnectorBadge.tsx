import { motion } from 'framer-motion';

interface Props {
  name: string;
  icon: React.ReactNode;
  index: number;
}

export default function ConnectorBadge({ name, icon, index }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: 0.8 + index * 0.08, duration: 0.4 }}
      className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.03] text-sm text-white/50 hover:text-white/80 hover:border-brand/25 transition-all duration-200 cursor-default"
      style={{ padding: '8px 16px' }}
    >
      <span className="text-brand/60">{icon}</span>
      {name}
    </motion.div>
  );
}

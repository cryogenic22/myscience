import React, { useState } from 'react';

interface InputProps {
  variant?: 'default' | 'search';
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit?: () => void;
}

const SearchIcon = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 16 16"
    fill="none"
    style={{ flexShrink: 0 }}
  >
    <circle cx="7" cy="7" r="5.5" stroke="var(--text-tertiary)" strokeWidth="1.5" />
    <line x1="11" y1="11" x2="14" y2="14" stroke="var(--text-tertiary)" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

export default function Input({
  variant = 'default',
  placeholder,
  value,
  onChange,
  onSubmit,
}: InputProps) {
  const [focused, setFocused] = useState(false);
  const isSearch = variant === 'search';

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && onSubmit) {
      onSubmit();
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: isSearch ? 'var(--space-2) var(--space-4)' : 'var(--space-2) var(--space-3)',
        borderRadius: isSearch ? 'var(--radius-full)' : 'var(--radius-md)',
        border: `1px solid ${focused ? 'var(--accent)' : 'var(--text-tertiary)'}`,
        backgroundColor: 'var(--surface-primary)',
        transition: `border-color var(--duration-fast) var(--ease-out)`,
      }}
    >
      {isSearch && <SearchIcon />}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        style={{
          flex: 1,
          border: 'none',
          outline: 'none',
          backgroundColor: 'transparent',
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-base)',
          color: 'var(--text-primary)',
          lineHeight: 1.5,
        }}
      />
    </div>
  );
}

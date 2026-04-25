'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { useCity, type City } from '@/app/lib/CityContext';

const LINKS: { href: string; label: string; primary?: boolean }[] = [
  { href: '/map', label: 'Map' },
  { href: '/zones', label: 'Zones' },
  { href: '/warnings', label: 'Warnings' },
  { href: '/patrol', label: 'Patrol' },
  { href: '/policy', label: 'Policy' },
  { href: '/decision', label: 'Decision', primary: true },
];

const CITY_OPTIONS: { value: City; label: string }[] = [
  { value: 'all', label: 'All Cities' },
  { value: 'nyc', label: 'New York City' },
  { value: 'london', label: 'London' },
];

export default function NavBar() {
  const pathname = usePathname() ?? '';
  const [menuOpen, setMenuOpen] = useState(false);
  const { city, setCity } = useCity();
  return (
    <nav className="site-nav" aria-label="Primary">
      <Link
        href="/"
        className={`site-nav-brand${pathname === '/' ? ' site-nav-brand-active' : ''}`}
        aria-current={pathname === '/' ? 'page' : undefined}
        onClick={() => setMenuOpen(false)}
      >
        Traffic-lyt
      </Link>
      <button
        className="site-nav-hamburger"
        aria-label={menuOpen ? 'Close menu' : 'Open menu'}
        aria-expanded={menuOpen}
        onClick={() => setMenuOpen((o) => !o)}
      >
        {menuOpen ? '✕' : '☰'}
      </button>
      <div className={`site-nav-links${menuOpen ? ' nav-open' : ''}`}>
        {LINKS.map((l) => {
          const active = pathname === l.href || pathname.startsWith(l.href + '/');
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`site-nav-link${l.primary ? ' site-nav-link-action' : ''}${active ? ' site-nav-link-active' : ''}`}
              aria-current={active ? 'page' : undefined}
              onClick={() => setMenuOpen(false)}
            >
              {l.label}
            </Link>
          );
        })}
        <select
          value={city}
          onChange={(e) => setCity(e.target.value as City)}
          aria-label="Select city"
          style={{
            background: '#1e293b',
            color: '#e2e8f0',
            border: '1px solid #475569',
            borderRadius: 6,
            padding: '0.3rem 0.5rem',
            fontSize: '0.875rem',
            cursor: 'pointer',
            marginLeft: '0.25rem',
          }}
        >
          {CITY_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>
    </nav>
  );
}

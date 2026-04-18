'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const LINKS: { href: string; label: string; primary?: boolean }[] = [
  { href: '/map', label: 'Map' },
  { href: '/zones', label: 'Zones' },
  { href: '/warnings', label: 'Warnings' },
  { href: '/patrol', label: 'Patrol' },
  { href: '/policy', label: 'Policy' },
  { href: '/decision', label: 'Decision', primary: true },
];

export default function NavBar() {
  const pathname = usePathname() ?? '';
  const [menuOpen, setMenuOpen] = useState(false);
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
      </div>
    </nav>
  );
}

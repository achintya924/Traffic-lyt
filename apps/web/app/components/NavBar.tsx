'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/map', label: 'Map' },
  { href: '/zones', label: 'Zones' },
  { href: '/warnings', label: 'Warnings' },
  { href: '/patrol', label: 'Patrol' },
  { href: '/policy', label: 'Policy' },
];

export default function NavBar() {
  const pathname = usePathname() ?? '';
  return (
    <nav className="site-nav" aria-label="Primary">
      <Link href="/" className="site-nav-brand">Traffic-lyt</Link>
      <div className="site-nav-links">
        {LINKS.map((l) => {
          const active = pathname === l.href || pathname.startsWith(l.href + '/');
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`site-nav-link${active ? ' site-nav-link-active' : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              {l.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

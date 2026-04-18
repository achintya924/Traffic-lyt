'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';

type Phase = 'idle' | 'start' | 'loading' | 'done';

export default function NavigationProgress() {
  const pathname = usePathname();
  const [phase, setPhase] = useState<Phase>('idle');
  const prevPathRef = useRef(pathname);
  const activeRef = useRef(false);
  const doneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const a = (e.target as HTMLElement).closest('a[href]');
      if (!a) return;
      const href = (a as HTMLAnchorElement).href;
      if (!href) return;
      try {
        const u = new URL(href);
        if (u.origin !== location.origin) return;
        if (u.pathname === location.pathname && u.search === location.search) return;
      } catch {
        return;
      }
      if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
      activeRef.current = true;
      setPhase('start');
      requestAnimationFrame(() => requestAnimationFrame(() => setPhase('loading')));
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  useEffect(() => {
    if (pathname === prevPathRef.current) return;
    prevPathRef.current = pathname;
    if (!activeRef.current) return;
    activeRef.current = false;
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    setPhase('done');
    doneTimerRef.current = setTimeout(() => setPhase('idle'), 450);
  }, [pathname]);

  if (phase === 'idle') return null;

  const widthMap: Record<Phase, string> = {
    idle: '0%', start: '0%', loading: '78%', done: '100%',
  };
  const opacityMap: Record<Phase, number> = {
    idle: 0, start: 1, loading: 1, done: 0,
  };
  const transitionMap: Record<Phase, string> = {
    idle: 'none',
    start: 'none',
    loading: 'width 2.5s cubic-bezier(0.05, 0.9, 0.5, 1)',
    done: 'width 0.12s ease-out, opacity 0.3s ease 0.12s',
  };

  return (
    <div
      aria-hidden="true"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        height: '3px',
        width: widthMap[phase],
        opacity: opacityMap[phase],
        background: '#2563eb',
        zIndex: 9999,
        pointerEvents: 'none',
        transition: transitionMap[phase],
        boxShadow: '0 0 10px rgba(37, 99, 235, 0.6)',
      }}
    />
  );
}

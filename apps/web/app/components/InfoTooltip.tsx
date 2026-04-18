'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

type Props = { text: string };

export default function InfoTooltip({ text }: Props) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, above: false });
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearHide = () => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
  };

  const scheduleHide = () => {
    hideTimer.current = setTimeout(() => setVisible(false), 120);
  };

  const show = useCallback(() => {
    clearHide();
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const popW = 260;
    const popH = 80; // rough estimate; tooltip never overflows due to fixed max-width
    const above = rect.bottom + popH > vh * 0.88;
    let left = rect.left + rect.width / 2 - popW / 2;
    if (left + popW > vw - 8) left = vw - popW - 8;
    if (left < 8) left = 8;
    const top = above ? rect.top - popH - 6 : rect.bottom + 6;
    setPos({ top, left, above });
    setVisible(true);
  }, []);

  const hide = useCallback(() => {
    clearHide();
    scheduleHide();
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!visible) return;
    const handler = (e: MouseEvent) => {
      if (
        btnRef.current?.contains(e.target as Node) ||
        popRef.current?.contains(e.target as Node)
      ) return;
      setVisible(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [visible]);

  useEffect(() => () => clearHide(), []);

  return (
    <>
      <button
        ref={btnRef}
        className="info-tooltip-btn"
        aria-label="More information"
        onMouseEnter={show}
        onMouseLeave={hide}
        onClick={(e) => { e.stopPropagation(); visible ? setVisible(false) : show(); }}
        type="button"
      >
        i
      </button>
      {visible &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={popRef}
            className="info-tooltip-popover"
            style={{ top: pos.top, left: pos.left }}
            onMouseEnter={clearHide}
            onMouseLeave={hide}
          >
            {text}
          </div>,
          document.body
        )}
    </>
  );
}

import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Patrol Allocation',
  description:
    'Allocate patrol units across NYC zones using a deterministic risk-priority scoring strategy with explainable reason chips.',
};

export default function PatrolLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

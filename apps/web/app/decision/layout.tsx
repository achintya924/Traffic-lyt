import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Decision Dashboard',
  description:
    'Get a unified "what should I do right now?" recommendation with full supporting evidence: verdict, confidence, hotspots, patrol plan, and forecast.',
};

export default function DecisionLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

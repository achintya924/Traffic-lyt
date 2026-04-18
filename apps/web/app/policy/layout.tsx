import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Policy Simulator',
  description:
    'Model enforcement interventions — intensity, patrol units, peak-hour reduction — and preview their impact against the violation forecast baseline.',
};

export default function PolicyLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

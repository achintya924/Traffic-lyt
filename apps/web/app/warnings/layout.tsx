import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Early Warnings',
  description:
    'Automatic warning signals for traffic volume spikes, week-over-week anomalies, and spatial anomaly cluster events.',
};

export default function WarningsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

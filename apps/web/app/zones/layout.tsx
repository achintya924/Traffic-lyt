import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Zone Analytics',
  description:
    'Browse neighborhood zone rankings, inspect violation trends and time-series, and compare zones side by side.',
};

export default function ZonesLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

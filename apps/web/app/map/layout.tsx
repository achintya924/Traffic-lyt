import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Live Map',
  description:
    'Explore NYC traffic violation markers, animated heatmap overlays, and predicted risk hotspots across the five boroughs in real time.',
};

export default function MapLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

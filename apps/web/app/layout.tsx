import type { Metadata } from 'next';
import './globals.css';
import NavBar from './components/NavBar';
import NavigationProgress from './components/NavigationProgress';

export const metadata: Metadata = {
  title: {
    template: 'Traffic-lyt | %s',
    default: 'Traffic-lyt',
  },
  description:
    'Real-time traffic violation analytics and predictive decision support for NYC smart cities.',
  openGraph: {
    title: 'Traffic-lyt',
    description:
      'Real-time traffic violation analytics and predictive decision support for NYC smart cities.',
    type: 'website',
  },
  icons: {
    icon: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <NavigationProgress />
        <NavBar />
        {children}
      </body>
    </html>
  );
}

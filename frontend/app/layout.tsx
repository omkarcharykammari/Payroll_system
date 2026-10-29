import './globals.css' ;
import { Providers } from '@/lib/providers';

export const metadata = {
  title: 'Vertex HR & Payroll',
  description: 'Enterprise HR and Payroll SaaS platform.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900 antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
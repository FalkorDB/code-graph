import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Toaster } from '@/components/ui/toaster'
import GoogleAnalytics from './components/GoogleAnalytics'
import { cn } from '@/lib/utils'
import GTM from './GTM'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Code Graph by FalkorDB',
  description: 'Code Graph visualization application by FalkorDB',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={cn(inter.className, "relative")}>
        <GTM />
        {children}
        <Toaster />
      </body>
    </html>
  )
}

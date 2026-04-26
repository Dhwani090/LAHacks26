// AppShell — shared chrome (brand + nav + status chip + brain monitor pane).
// Wraps /predict and /library so the brain monitor can keep rendering across
// page transitions and BrainFrame state stays alive in the right pane.
// Homepage uses its own layout — see app/page.tsx.
// See docs/PRD.md §7.
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { type ReactNode } from 'react';
import { BrainMonitor } from './BrainMonitor';
import { StatusChip } from './StatusChip';

const NAV: { href: string; label: string }[] = [
  { href: '/predict', label: 'Predict' },
  { href: '/library', label: 'Library' },
];

interface Props {
  children: ReactNode;
  showBrainPane?: boolean;
  subtitle?: string;
}

export function AppShell({ children, showBrainPane = true, subtitle }: Props) {
  const pathname = usePathname();
  return (
    <main className="relative flex h-screen w-screen overflow-hidden bg-[#0a0a12] text-white">
      <section className="flex min-w-0 flex-1 flex-col gap-6 px-8 py-7">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="group">
              <h1 className="text-sm font-medium uppercase tracking-[0.3em] text-white/70 group-hover:text-white">
                Cortex
              </h1>
              <p className="mt-1 text-xs text-white/40">
                {subtitle ?? "predict what the average viewer's brain did with your work"}
              </p>
            </Link>
            <nav className="flex items-center gap-1 text-xs uppercase tracking-[0.22em]">
              {NAV.map((item) => {
                const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`rounded-full border px-4 py-1.5 transition-colors ${
                      active
                        ? 'border-orange-400/60 bg-orange-400/10 text-orange-200'
                        : 'border-white/10 text-white/55 hover:border-white/30 hover:text-white/85'
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <StatusChip />
        </header>

        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </section>

      {showBrainPane && (
        <aside className="relative w-[42%] min-w-[420px] border-l border-white/10 bg-black/40">
          <BrainMonitor />
          <div className="pointer-events-none absolute bottom-4 right-5 text-[10px] uppercase tracking-[0.25em] text-white/30">
            fsaverage5 · z-scored BOLD
          </div>
        </aside>
      )}
    </main>
  );
}

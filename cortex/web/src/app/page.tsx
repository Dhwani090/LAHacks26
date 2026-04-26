// Homepage — landing surface for Cortex's two pillars.
// PRD §1 (vision) + §6.3 / §11.6.
// /predict = upload + brain visualization + engagement prediction + originality search.
// /library = creator's past clips (TRIBE features + transcripts; no raw mp4s).
// See docs/PRD.md §1.
import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="relative flex h-screen w-screen flex-col overflow-hidden bg-[#0a0a12] text-white">
      <header className="flex items-center justify-between px-8 py-6">
        <div>
          <h1 className="text-sm font-medium uppercase tracking-[0.32em] text-white/80">Cortex</h1>
          <p className="mt-1 text-xs text-white/45">
            predict what the average viewer&apos;s brain did with your work
          </p>
        </div>
        <div className="text-[10px] uppercase tracking-[0.25em] text-white/30">
          TRIBE v2 · fsaverage5 · GX10 local
        </div>
      </header>

      <section className="flex flex-1 flex-col items-center justify-center gap-12 px-8">
        <div className="max-w-2xl text-center">
          <h2 className="text-3xl font-semibold leading-tight text-white/90 sm:text-4xl">
            Two questions every short-form creator asks before they post.
          </h2>
          <p className="mt-4 text-sm leading-relaxed text-white/55">
            We answer both with one signal: a neuroscience model predicting what an
            average viewer&apos;s brain does with your draft, second by second.
          </p>
        </div>

        <div className="grid w-full max-w-4xl grid-cols-1 gap-4 sm:grid-cols-2">
          <NavCard
            href="/predict"
            label="Predict"
            tagline="Will this work?"
            body="Drop a video. Watch the brain. Click predict to see expected engagement vs. your follower size and a percentile rank against our seed corpus."
            cta="Upload draft"
            tone="orange"
          />
          <NavCard
            href="/library"
            label="Library"
            tagline="Are you repeating yourself?"
            body="Past clips persist as TRIBE features + transcripts (no raw video). Once you have 5+ in your library, every new draft surfaces its closest brain-twin from your back catalog."
            cta="Manage past clips"
            tone="indigo"
          />
        </div>

        <div className="text-[11px] uppercase tracking-[0.22em] text-white/30">
          everything runs on the box · nothing leaves your network
        </div>
      </section>
    </main>
  );
}

interface NavCardProps {
  href: string;
  label: string;
  tagline: string;
  body: string;
  cta: string;
  tone: 'orange' | 'indigo';
}

function NavCard({ href, label, tagline, body, cta, tone }: NavCardProps) {
  const accent =
    tone === 'orange'
      ? 'border-orange-400/30 hover:border-orange-400/60 hover:bg-orange-400/5'
      : 'border-indigo-400/30 hover:border-indigo-400/60 hover:bg-indigo-400/5';
  const ctaColor =
    tone === 'orange' ? 'text-orange-200' : 'text-indigo-200';
  return (
    <Link
      href={href}
      className={`group flex flex-col justify-between gap-6 rounded-lg border bg-white/[0.03] p-6 transition-colors ${accent}`}
    >
      <div className="flex flex-col gap-2">
        <div className="text-[10px] uppercase tracking-[0.28em] text-white/45">{label}</div>
        <div className="text-2xl font-semibold text-white/90">{tagline}</div>
        <p className="text-sm leading-relaxed text-white/55">{body}</p>
      </div>
      <div className={`text-xs uppercase tracking-[0.22em] ${ctaColor}`}>
        {cta} →
      </div>
    </Link>
  );
}

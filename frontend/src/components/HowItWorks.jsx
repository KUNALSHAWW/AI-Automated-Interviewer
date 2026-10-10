const STEPS = [
  ['1. Nova reads your repository', 'Public GitHub repos only. The stack is read from manifests, file paths and the README with plain rules (no model), so it is reproducible.'],
  ['2. You present, Nova listens and watches', 'Your browser detects when you pause, so whole utterances are transcribed. Slides are described only when the picture really changed.'],
  ['3. Said vs shown vs built', 'If you name a tool that is nowhere in your repository, or a slide draws one that is not built, Nova asks about it. It never accuses.'],
  ['4. Every score needs a quote', 'The model must copy a verbatim quote for each score. Code checks the quote exists in your transcript or on screen; otherwise the score is discarded.'],
  ['5. A small panel of models grades', 'Up to three different model families grade only what was observed. Scores that disagree are flagged for a human instead of being averaged away.'],
]

const LIMITS = [
  'Speech recognition errs on accents and technical words; Nova passes your repo\'s stack names to the recogniser to help.',
  'The repository check reads a sample (manifests, tree, README, a few key files). "Not found" means "worth asking", not "false".',
  'Models can misjudge. The report is advisory feedback, flags itself when evidence is thin, and should not be the only input to a grade or a hiring decision.',
  'Free provider tiers have rate limits. Nova names the provider and the reason when something is unavailable, and never invents a score to fill the gap.',
]

export default function HowItWorks() {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-3xl font-bold">How NavAI Viva works</h2>
        <p className="text-blue-200 mt-2">
          Written work is easy to generate; understanding is not. Oral defense of your own project is the check that is hard to outsource,
          but it does not scale to every student or hackathon team. NavAI Viva makes it scale and shows its work.
        </p>
      </div>
      <div className="space-y-3">
        {STEPS.map(([h, t]) => (
          <div key={h} className="glass-card p-4"><div className="font-semibold">{h}</div><div className="text-sm text-white/70 mt-1">{t}</div></div>
        ))}
      </div>
      <div className="glass-card p-5">
        <h3 className="font-semibold mb-2">Honest limits</h3>
        <ul className="list-disc ml-5 text-sm text-white/70 space-y-1">{LIMITS.map((l) => <li key={l}>{l}</li>)}</ul>
      </div>
    </div>
  )
}

// Single source of truth for brand + links. Swap the name/links here and the whole site
// updates — including <title>, nav, and CTAs.
export const SITE = {
  name: "Agentry",
  tagline: "Production AI agents, shipped in weeks — not quarters.",
  description:
    "Agentry is an independent AI-agent studio. We design, build, and ship autonomous AI agents end to end — architecture, orchestration, evals, deploy, and the production concerns most demos skip.",
  // Booking link reused from your outreach config (Calendly). Email + url are placeholders
  // until the domain is registered — update both here and everything across the site follows.
  calUrl: "https://calendly.com/hello-contentdrip/chance-beyer-intro",
  email: "hello@contentdrip.ai",
  url: "https://agentry.contentdrip.ai",
} as const;

export const NAV = [
  { href: "/#work", label: "Work" },
  { href: "/#services", label: "What we build" },
  { href: "/blog", label: "Blog" },
  { href: "/writing", label: "Case Studies" },
  { href: "/tools", label: "Free tools" },
  { href: "/audit", label: "Free AI audit" },
] as const;

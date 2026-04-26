// Single-creator constant for the hackathon build.
// PRD §11.6 caveat: multi-tenant + auth comes after the hackathon. Every
// /library/upload, /library/{id}, and /similarity request uses this id.
// Centralized here so renaming is a one-line change.
export const DEMO_CREATOR_ID = 'demo';

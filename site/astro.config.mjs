import { defineConfig } from 'astro/config';
import vercel from '@astrojs/vercel';

// Deployed on Vercel at https://birdsbugsbotanicals.marcuslevine.com
// SSR is required because /app calls server-side API functions (see api/)
// that shell out to the Python content pipeline and the TikTok OAuth flow,
// so this can no longer be a purely static GitHub Pages site.
export default defineConfig({
  site: 'https://birdsbugsbotanicals.marcuslevine.com',
  output: 'server',
  adapter: vercel(),
});

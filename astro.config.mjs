// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';
import react from '@astrojs/react';

export default defineConfig({
  site: 'https://www.catalinaskitchen.com',
  output: 'static',
  adapter: vercel({
    webAnalytics: { enabled: false },
  }),
  integrations: [
    react(),
    sitemap({
      filter: (page) => ![
        'https://www.catalinaskitchen.com/privacy-policy/',
        'https://www.catalinaskitchen.com/contact/',
      ].includes(page),
    }),
  ],
  vite: {
    plugins: [tailwindcss()],
    ssr: {
      noExternal: ['@contentful/rich-text-html-renderer'],
    },
  },
});

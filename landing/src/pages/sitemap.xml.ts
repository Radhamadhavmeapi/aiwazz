import type { APIRoute } from "astro";

const PAGES = [
  { path: "/", priority: "1.0" },
  { path: "/text-to-speech/", priority: "0.8" },
  { path: "/hindi-text-to-speech/", priority: "0.8" },
  { path: "/ai-voiceover-for-reels/", priority: "0.8" },
];

export const GET: APIRoute = ({ site }) => {
  const lastmod = new Date().toISOString().slice(0, 10);
  const urls = PAGES.map(
    (p) => `  <url><loc>${new URL(p.path, site).href}</loc><lastmod>${lastmod}</lastmod><priority>${p.priority}</priority></url>`,
  ).join("\n");
  return new Response(`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
};

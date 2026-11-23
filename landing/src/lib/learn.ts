// Learn guides: content/learn/*.md → static pages at their front-matter slug.
// Code blocks are highlighted at build time with Shiki (light + dark via CSS variables).
import { Marked } from "marked";
import { createHighlighter } from "shiki";

const raw = import.meta.glob<string>("../../../content/learn/*.md", { query: "?raw", import: "default", eager: true });

// ids are the exact `category:` values used in content/learn/*.md front matter
export const CATEGORIES = [
  { id: "Start here", label: "Start here", icon: "rocket" },
  { id: "Better results", label: "Better results", icon: "sparkles" },
  { id: "Developers", label: "Developers", icon: "code-xml" },
  { id: "Account and billing", label: "Account and billing", icon: "user-round" },
  { id: "Help", label: "Help", icon: "life-buoy" },
] as const;

export type Guide = {
  file: string;
  slug: string; // e.g. "getting-started" ("" for the hub)
  url: string;
  title: string;
  metaTitle: string;
  metaDescription: string;
  order: number;
  category: string;
  html: string;
  toc: { id: string; text: string }[];
  text: string; // plain text for search
  faq: { q: string; a: string }[]; // H2 + first paragraph (used for FAQPage on troubleshooting)
};

const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/&[a-z]+;/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");

function frontMatter(src: string) {
  const m = src.match(/^---\n([\s\S]*?)\n---\n?/);
  const data: Record<string, string> = {};
  if (m)
    for (const line of m[1].split("\n")) {
      const i = line.indexOf(":");
      if (i > 0) data[line.slice(0, i).trim()] = line.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    }
  return { data, body: m ? src.slice(m[0].length) : src };
}

let highlighter: Awaited<ReturnType<typeof createHighlighter>> | null = null;
async function hl() {
  highlighter ??= await createHighlighter({
    themes: ["github-light", "github-dark"],
    langs: ["bash", "json", "python", "js", "ts", "tsx", "jsx", "html"],
  });
  return highlighter;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function render(md: string) {
  // 1. pull out fenced code, highlight it, put placeholders in the markdown
  const blocks: string[] = [];
  const h = await hl();
  md = md.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang = "text", code: string) => {
    const l = h.getLoadedLanguages().includes(lang) ? lang : "text";
    const html = h.codeToHtml(code.replace(/\n$/, ""), { lang: l, themes: { light: "github-light", dark: "github-dark" }, defaultColor: false });
    blocks.push(
      `<div class="code-block"><div class="code-bar"><span>${esc(lang)}</span><button type="button" class="copy-code" aria-label="Copy code">Copy</button></div>${html}</div>`,
    );
    return `\n<!--CODE:${blocks.length - 1}-->\n`;
  });
  // 2. markdown → HTML with heading ids, TOC and safe external links
  const toc: { id: string; text: string }[] = [];
  const marked = new Marked({ gfm: true });
  marked.use({
    renderer: {
      heading({ tokens, depth }) {
        const text = this.parser.parseInline(tokens);
        const id = slugify(text);
        if (depth === 2) toc.push({ id, text: text.replace(/<[^>]+>/g, "") });
        return `<h${depth} id="${id}">${text}</h${depth}>\n`;
      },
      link({ href, title, tokens }) {
        const text = this.parser.parseInline(tokens);
        const external = /^https?:\/\//.test(href) && !href.startsWith("https://aiwazz.in");
        const t = title ? ` title="${title}"` : "";
        return external ? `<a href="${href}"${t} target="_blank" rel="noopener">${text}</a>` : `<a href="${href}"${t}>${text}</a>`;
      },
    },
  });
  let html = marked.parse(md) as string;
  html = html
    .replace(/<!--CODE:(\d+)-->/g, (_, i) => blocks[Number(i)])
    .replace(/<table>/g, '<div class="table-wrap"><table>')
    .replace(/<\/table>/g, "</table></div>");
  return { html, toc };
}

function plain(md: string) {
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#>*`|_\-]+/g, " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function faqFrom(md: string) {
  return [...md.matchAll(/^## (.+)\n+([^\n#][^\n]*)/gm)].map((m) => ({
    q: m[1].trim(),
    a: m[2].replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/\*\*/g, "").trim(),
  }));
}

let cache: Guide[] | null = null;
export async function loadGuides(): Promise<Guide[]> {
  if (cache) return cache;
  const out: Guide[] = [];
  for (const [path, src] of Object.entries(raw)) {
    const file = path.split("/").pop()!;
    const { data, body } = frontMatter(src);
    const title = body.match(/^# (.+)$/m)?.[1] ?? data.title;
    const content = body.replace(/^# .+\n+/m, "");
    const { html, toc } = await render(content);
    const slug = (data.slug || "").replace(/^\/learn\/?|\/$/g, "");
    out.push({
      file,
      slug,
      url: `/learn/${slug ? `${slug}/` : ""}`,
      title,
      metaTitle: data.metaTitle || `${title} | AiWazz Learn`,
      metaDescription: data.metaDescription || "",
      order: Number(data.order ?? 99),
      category: data.category || "Help",
      // unknown categories would silently vanish from the sidebar: fail the build instead
      html,
      toc,
      text: plain(content),
      faq: faqFrom(content),
    });
  }
  for (const g of out)
    if (g.slug && !CATEGORIES.some((c) => c.id === g.category)) throw new Error(`content/learn/${g.file}: unknown category "${g.category}"`);
  cache = out.sort((a, b) => a.order - b.order);
  return cache;
}

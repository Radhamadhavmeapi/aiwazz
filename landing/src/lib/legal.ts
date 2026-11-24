// Legal/policy pages: legal/pages/*.md + legal/legal.json (single source of truth).
// - {{dotted.tokens}} are filled from legal.json; an unknown token fails the build.
// - Empty values (e.g. llpin) are never published: the fragment "(LABEL {{x}}, " or the whole
//   list item / table row / line holding it is removed.
// - <!-- Implementation: … --> comments are instructions for developers and are stripped.
import { Marked } from "marked";
import legal from "../../../legal/legal.json";

export const LEGAL = legal as typeof legal & Record<string, unknown>;
const raw = import.meta.glob<string>("../../../legal/pages/*.md", { query: "?raw", import: "default", eager: true });

export type LegalPage = {
  file: string;
  slug: string; // "terms" (no slashes)
  title: string;
  metaTitle: string;
  metaDescription: string;
  html: string;
  toc: { id: string; text: string }[];
  markdown: string;
};

function lookup(path: string): unknown {
  return path.split(".").reduce<unknown>((o, k) => (o == null ? undefined : (o as Record<string, unknown>)[k]), legal);
}

export const missingValues = new Set<string>();

function fillTokens(md: string, file: string): string {
  // 1. tokens whose value is empty: drop the smallest sensible piece of text around them
  md = md.replace(/\{\{([\w.]+)\}\}/g, (m, path) => {
    const v = lookup(path);
    if (v === undefined) throw new Error(`legal/pages/${file}: unknown token ${m}`);
    return v === "" || v === null ? `\u0000${path}\u0000` : m;
  });
  if (md.includes("\u0000")) {
    md = md
      .replace(/[A-Z][A-Za-z]* \u0000[\w.]+\u0000, /g, "") // "(LLPIN {{llpin}}, GSTIN …)" → "(GSTIN …)"
      .split("\n")
      .filter((line) => {
        const m = line.match(/\u0000([\w.]+)\u0000/);
        if (m) missingValues.add(m[1]);
        return !m; // list item, table row or line containing an empty value
      })
      .join("\n");
  }
  // 2. remaining tokens → values
  return md.replace(/\{\{([\w.]+)\}\}/g, (_, path) => String(lookup(path)));
}

const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");

function render(md: string) {
  const toc: { id: string; text: string }[] = [];
  const marked = new Marked({ gfm: true, breaks: false });
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
  // tables scroll horizontally on phones instead of breaking the layout
  const html = (marked.parse(md) as string).replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, "</table></div>");
  return { html, toc };
}

function frontMatter(src: string) {
  const m = src.match(/^---\n([\s\S]*?)\n---\n?/);
  const data: Record<string, string> = {};
  if (m) for (const line of m[1].split("\n")) {
    const i = line.indexOf(":");
    if (i > 0) data[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { data, body: m ? src.slice(m[0].length) : src };
}

export function loadLegalPages(): LegalPage[] {
  return Object.entries(raw)
    .map(([path, src]) => {
      const file = path.split("/").pop()!;
      const { data, body } = frontMatter(src);
      const markdown = fillTokens(body.replace(/<!--\s*Implementation:[\s\S]*?-->/g, "").trim(), file);
      const title = markdown.match(/^# (.+)$/m)?.[1] ?? data.title;
      const { html, toc } = render(markdown.replace(/^# .+\n+/m, "")); // H1 is rendered by the layout
      return {
        file,
        slug: (data.slug || "").replace(/^\/|\/$/g, ""),
        title: fillTokens(title ?? "", file),
        metaTitle: fillTokens(data.metaTitle || data.title, file),
        metaDescription: fillTokens(data.metaDescription || "", file),
        html,
        toc,
        markdown,
      };
    })
    .sort((a, b) => a.slug.localeCompare(b.slug));
}

export const legalPage = (slug: string) => {
  const p = loadLegalPages().find((x) => x.slug === slug);
  if (!p) throw new Error(`No legal page ${slug}`);
  return p;
};

export const fmtINR = (n: number) => `₹${n.toLocaleString("en-IN")}`;

/** Yearly = exactly 12 × the discounted monthly price (each rounded to whole rupees), so the two never disagree. */
export const planPrice = (priceMonthly: number) => {
  const yearlyPerMonth = Math.round(priceMonthly * (1 - LEGAL.yearlyDiscountPercent / 100));
  return { monthly: priceMonthly, yearlyPerMonth, yearly: yearlyPerMonth * 12 };
};

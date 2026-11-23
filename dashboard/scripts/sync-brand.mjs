// Copies shared brand assets (design/assets, built from brand/ by tools/brand_assets.py) into public/.
// public/ is generated: favicon set at the site root, logos/icons under brand/, og-image.png.
import { cpSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "../../design/assets");
const pub = join(here, "../public");
rmSync(pub, { recursive: true, force: true });
mkdirSync(join(pub, "brand"), { recursive: true });
cpSync(join(src, "favicon"), pub, { recursive: true });
cpSync(join(src, "og-image.png"), join(pub, "og-image.png"));
for (const f of readdirSync(src)) if (f.endsWith(".webp")) cpSync(join(src, f), join(pub, "brand", f));
// login.aiwazz.in is an app, not content: keep crawlers out of the API and the design preview
writeFileSync(join(pub, "robots.txt"), "User-agent: *\nDisallow: /api/\nDisallow: /preview/\n");
writeFileSync(join(pub, "llms.txt"), "# AiWazz app\n\n> Sign-in and dashboard for AiWazz, AI text to speech in Hindi, Hinglish and English.\n\n- [Sign in](https://login.aiwazz.in/login)\n- [Create an account](https://login.aiwazz.in/signup)\n- [Product site](https://aiwazz.in/)\n- [Docs](https://aiwazz.in/learn/)\n- [API quickstart](https://aiwazz.in/learn/api-quickstart/)\n");
console.log("brand assets synced to public/");

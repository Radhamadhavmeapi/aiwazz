// public/ is generated: favicon set + og-image at the site root, brand webp under /brand,
// voice samples under /samples (from landing/samples, made by tools/make_samples.py).
import { cpSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, "../../design/assets");
const pub = join(here, "../public");
rmSync(pub, { recursive: true, force: true });
mkdirSync(join(pub, "brand"), { recursive: true });
mkdirSync(join(pub, "samples"), { recursive: true });
cpSync(join(assets, "favicon"), pub, { recursive: true });
cpSync(join(assets, "og-image.png"), join(pub, "og-image.png"));
for (const f of readdirSync(assets)) if (f.endsWith(".webp")) cpSync(join(assets, f), join(pub, "brand", f));
for (const f of readdirSync(join(here, "../samples"))) if (f.endsWith(".mp3")) cpSync(join(here, "../samples", f), join(pub, "samples", f));
console.log("brand assets + samples synced to public/");

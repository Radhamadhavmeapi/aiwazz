// @ts-check
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://aiwazz.in",
  output: "static",
  trailingSlash: "always",
  compressHTML: true,
  // directory output: /page/index.html works on aaPanel nginx without try_files changes
  build: { format: "directory", inlineStylesheets: "always" },
  vite: { plugins: [tailwindcss()] },
});

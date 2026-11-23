// Theme toggle (remembered) + mobile menu. Tiny, no framework.
const root = document.documentElement;
const meta = document.querySelector('meta[name="theme-color"]');
function setTheme(t: "dark" | "light") {
  root.classList.remove("dark", "light");
  root.classList.add(t);
  meta?.setAttribute("content", t === "dark" ? "#0a0a0b" : "#f4f6fb");
  try {
    localStorage.setItem("aiwazz-theme", t);
  } catch {
    /* private mode */
  }
  document.querySelectorAll<HTMLButtonElement>("[data-theme-toggle]").forEach((b) => {
    b.setAttribute("aria-label", t === "dark" ? "Switch to light theme" : "Switch to dark theme");
  });
  window.dispatchEvent(new CustomEvent("aiwazz:theme"));
}
document.querySelectorAll<HTMLButtonElement>("[data-theme-toggle]").forEach((b) =>
  b.addEventListener("click", () => setTheme(root.classList.contains("light") ? "dark" : "light")),
);

const menuBtn = document.querySelector<HTMLButtonElement>("[data-menu-toggle]");
const menu = document.getElementById("mobile-menu");
menuBtn?.addEventListener("click", () => {
  const open = menuBtn.getAttribute("aria-expanded") === "true";
  menuBtn.setAttribute("aria-expanded", String(!open));
  menu?.toggleAttribute("hidden", open);
});
menu?.querySelectorAll("a").forEach((a) =>
  a.addEventListener("click", () => {
    menuBtn?.setAttribute("aria-expanded", "false");
    menu.setAttribute("hidden", "");
  }),
);

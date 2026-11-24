// Renders the PNG app icons from the logo mark (run once, the PNGs are committed):
//   node scripts/make-icons.mjs
// Phones want PNG: iOS ignores SVG for the home-screen icon, Android wants 192 and 512 px and a
// "maskable" one whose art stays inside the central safe zone because the launcher crops it.
import { chromium } from "@playwright/test";
import { writeFileSync } from "node:fs";

const mark = (scale, dx, dy) =>
  `<g transform="translate(${dx} ${dy}) scale(${scale})"><g fill="none" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"><path d="M17.6,14.7 A12,12 0 1 0 24.4,32"/><path d="M28,14 V38"/></g></g>`;
// Rounded tile (as the favicon) and full-bleed squares (the system rounds or masks those).
const rounded = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#1555DD"/>${mark(1, 17, 7)}</svg>`;
const square = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#1555DD"/>${mark(1, 17, 7)}</svg>`;
const maskable = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#1555DD"/>${mark(0.72, 21.2, 14)}</svg>`;

const icons = [
  ["public/icons/icon-192.png", rounded, 192, true],
  ["public/icons/icon-512.png", rounded, 512, true],
  ["public/icons/maskable-512.png", maskable, 512, false],
  ["public/icons/apple-touch-icon.png", square, 180, false],
];

// The installed Chrome, so the script needs no browser download.
const browser = await chromium.launch({ channel: "chrome" });
for (const [path, svg, size, transparent] of icons) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
  writeFileSync(path, await page.screenshot({ omitBackground: transparent }));
  await page.close();
  console.log(path);
}
await browser.close();

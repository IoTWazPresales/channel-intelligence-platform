/**
 * N-0018 implementer 1280×800 browser proof (Playwright setViewportSize).
 * Does not use CDP Emulation.setDeviceMetricsOverride.
 */
const fs = require("fs");
const path = require("path");
const { createRequire } = require("module");
const requireFromWeb = createRequire(
  path.resolve(__dirname, "../../../apps/web/package.json"),
);
const { chromium } = requireFromWeb("@playwright/test");

const OUT = path.resolve(__dirname);
const shots = path.join(OUT, "renders");
fs.mkdirSync(shots, { recursive: true });

async function headlines(page) {
  return page.evaluate(() => {
    const labels = [...document.querySelectorAll("p, span, div, h1, h2, h6")].map((el) =>
      (el.textContent || "").replace(/\s+/g, " ").trim(),
    );
    return {
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      title: document.querySelector("h1")?.textContent?.trim() || null,
      sample: labels.filter((t) => t.length > 0 && t.length < 80).slice(0, 80),
    };
  });
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const log = { viewport: "1280x800", pages: [] };

  async function visit(name, url) {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForTimeout(500);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page
      .getByText("Open shipments", { exact: false })
      .first()
      .waitFor({ timeout: 20_000 })
      .catch(() => {});
    await page.waitForTimeout(800);
    const info = await headlines(page);
    const file = path.join(shots, `${name}.png`);
    await page.screenshot({ path: file, fullPage: false });
    const rec = {
      name,
      requested: url,
      finalUrl: page.url(),
      screenshot: path.relative(OUT, file).replace(/\\/g, "/"),
      ...info,
    };
    log.pages.push(rec);
    return rec;
  }

  await visit("lab-supply", "http://127.0.0.1:3000/design-lab/supply");
  await visit("prod-supply", "http://127.0.0.1:3000/supply");

  const openShipments = page.getByRole("button", { name: /Open shipments/ }).first();
  if (await openShipments.count()) {
    await openShipments.click();
    await page.waitForTimeout(1500);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.screenshot({ path: path.join(shots, "prod-open-shipments-click.png"), fullPage: false });
    log.pages.push({
      name: "prod-open-shipments-click",
      finalUrl: page.url(),
      innerWidth: await page.evaluate(() => window.innerWidth),
    });
  }

  await visit("prod-receipts", "http://127.0.0.1:3000/admin/shipment-evidence");
  await visit("prod-po", "http://127.0.0.1:3000/admin/po-management");
  await visit("prod-stock-inbound-redirect", "http://127.0.0.1:3000/stock?lens=inbound");
  await visit("prod-shipping-redirect", "http://127.0.0.1:3000/shipping");

  fs.writeFileSync(path.join(OUT, "browser_1280.json"), JSON.stringify(log, null, 2));
  await browser.close();
  console.log(JSON.stringify({ ok: true, pages: log.pages.map((p) => ({ name: p.name, url: p.finalUrl, w: p.innerWidth })) }, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

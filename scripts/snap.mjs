import puppeteer from "puppeteer";
import { PDFDocument } from "pdf-lib";
import fs from "fs";

const BASE = process.env.BASE || "http://localhost:3000";
const PAGES = [
  `${BASE}/`,
  `${BASE}/deals`,
  `${BASE}/deals/1`,
  `${BASE}/trucking`,
  `${BASE}/positions/counterparty`,
  `${BASE}/positions/location`,
  `${BASE}/positions/security`,
  `${BASE}/positions/aging`,
  `${BASE}/swaps`,
  `${BASE}/losses`,
  `${BASE}/noic`,
  `${BASE}/documents`,
  `${BASE}/documents/1`,
  `${BASE}/master`,
  `${BASE}/master/entities`,
  `${BASE}/master/banks`,
  `${BASE}/master/counterparties`,
  `${BASE}/master/counterparties/1`,
  `${BASE}/master/products`,
  `${BASE}/master/locations`,
  `${BASE}/master/storage`,
];

const browser = await puppeteer.launch({
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});
const merged = await PDFDocument.create();

for (const url of PAGES) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900, deviceScaleFactor: 1 });
  await page.emulateMediaType("screen");
  console.log("→", url);
  try {
    await page.goto(url, { waitUntil: "networkidle0", timeout: 30000 });
    await new Promise(r => setTimeout(r, 300));
    const height = await page.evaluate(() => document.body.scrollHeight + 80);
    const pdfBuf = await page.pdf({
      printBackground: true, width: "1400px", height: height + "px",
      margin: { top: "20px", bottom: "20px", left: "20px", right: "20px" },
    });
    const doc = await PDFDocument.load(pdfBuf);
    const copied = await merged.copyPages(doc, doc.getPageIndices());
    copied.forEach((pg) => merged.addPage(pg));
  } catch (e) {
    console.error("  failed:", e.message);
  }
  await page.close();
}

const out = await merged.save();
fs.writeFileSync(process.argv[2] || "preview.pdf", out);
await browser.close();
console.log("Done");

import puppeteer from "puppeteer";
import { PDFDocument } from "pdf-lib";
import fs from "fs";

const PAGES = [
  { url: "http://localhost:3000/",                            title: "Dashboard" },
  { url: "http://localhost:3000/positions/counterparty",      title: "Positions — By Counterparty" },
  { url: "http://localhost:3000/positions/location",          title: "Positions — By Location & Product" },
  { url: "http://localhost:3000/deals",                       title: "Deals — List" },
  { url: "http://localhost:3000/deals/1",                     title: "Deal Detail (ETG sale)" },
  { url: "http://localhost:3000/deals/new",                   title: "New Deal Form" },
  { url: "http://localhost:3000/documents",                   title: "Documents — List" },
  { url: "http://localhost:3000/documents/1",                 title: "PFI Document (matches uploaded template)" },
  { url: "http://localhost:3000/documents/2",                 title: "Final Invoice Document" },
  { url: "http://localhost:3000/documents/new?type=PFI",      title: "New PFI — Pick a Deal" },
  { url: "http://localhost:3000/documents/new?type=PFI&deal_id=1", title: "New PFI — Bank + Details" },
  { url: "http://localhost:3000/documents/new?type=STORAGE_INVOICE", title: "New Storage Invoice" },
  { url: "http://localhost:3000/master",                      title: "Master Data — Overview" },
  { url: "http://localhost:3000/master/entities",             title: "Master — Entities" },
  { url: "http://localhost:3000/master/banks",                title: "Master — Banks" },
  { url: "http://localhost:3000/master/counterparties",       title: "Master — Counterparties" },
  { url: "http://localhost:3000/master/counterparties/1",     title: "Counterparty Detail (ETG)" },
  { url: "http://localhost:3000/master/products",             title: "Master — Products" },
  { url: "http://localhost:3000/master/locations",            title: "Master — Locations" },
  { url: "http://localhost:3000/master/storage",              title: "Master — Storage Agreements" },
];

const browser = await puppeteer.launch({
  headless: "new",
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
});
const merged = await PDFDocument.create();

for (const p of PAGES) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 900, deviceScaleFactor: 1 });
  await page.emulateMediaType("screen");
  console.log("→", p.url);
  await page.goto(p.url, { waitUntil: "networkidle0", timeout: 30000 });
  await new Promise(r => setTimeout(r, 300));
  const height = await page.evaluate(() => document.body.scrollHeight + 80);
  const pdfBuf = await page.pdf({
    printBackground: true,
    width: "1400px",
    height: height + "px",
    margin: { top: "20px", bottom: "20px", left: "20px", right: "20px" },
  });
  const doc = await PDFDocument.load(pdfBuf);
  const copied = await merged.copyPages(doc, doc.getPageIndices());
  copied.forEach((pg) => merged.addPage(pg));
  await page.close();
}

const out = await merged.save();
fs.writeFileSync(process.argv[2] || "/home/user/test/trading-ops-preview.pdf", out);
await browser.close();
console.log("Done");

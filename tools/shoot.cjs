// لقطات الشاشة وصور الأعمال، عبر Playwright.
//
// لقطة لصفحة (رابط أو ملف محلي):
//   node tools/shoot.cjs page <url|path> <out.png> [--desktop] [--click "نص"]... [--scroll 600]
// صورة عمل بهوية الموقع (1200x750) من لقطة أو لقطتين:
//   node tools/shoot.cjs thumb <out.png> <menu|site|video> <shot1.png> [shot2.png]
//
// يحتاج playwright: npm i playwright (أو ضع مساره في PLAYWRIGHT)، وكروميوم (أو مساره في CHROMIUM).
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const toUrl = s => (/^https?:|^file:/.test(s) ? s : pathToFileURL(path.resolve(s)).href);

async function page(b, args) {
  const [src, out] = args;
  const desktop = args.includes('--desktop');
  const ctx = await b.newContext(desktop
    ? { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1.5 }
    : { viewport: { width: 400, height: 820 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const p = await ctx.newPage();
  await p.goto(toUrl(src), { waitUntil: 'networkidle', timeout: 45000 });
  await p.waitForTimeout(800);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--click') {
      // يطابق النص بالضبط أولاً، وإذا ما لگاه يقبل جزءاً منه (مثل «تأكيد الطاولة ١٢»)
      const exact = p.getByText(args[i + 1], { exact: true });
      await ((await exact.count()) ? exact : p.getByText(args[i + 1])).first().click();
      await p.waitForTimeout(900);
    }
    if (args[i] === '--scroll') { await p.mouse.wheel(0, Number(args[i + 1])); await p.waitForTimeout(900); }
  }
  await p.screenshot({ path: out });
}

async function thumb(b, args) {
  const [out, kind, a, bb] = args;
  const p = await (await b.newContext({ viewport: { width: 1200, height: 750 } })).newPage();
  const qs = new URLSearchParams({ kind, a: toUrl(a), ...(bb ? { b: toUrl(bb) } : {}) });
  await p.goto(`${toUrl(path.join(__dirname, 'thumb.html'))}?${qs}`);
  await p.waitForFunction(() => [...document.images].every(i => i.complete && i.naturalWidth > 0));
  await p.screenshot({ path: out });
}

(async () => {
  const [mode, ...args] = process.argv.slice(2);
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  try {
    if (mode === 'page') await page(b, args);
    else if (mode === 'thumb') await thumb(b, args);
    else throw new Error('usage: shoot.cjs page|thumb ...');
  } finally {
    await b.close();
  }
})().catch(e => { console.error(e.message); process.exit(1); });

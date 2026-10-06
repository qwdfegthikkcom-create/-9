// فحص الموقع بعد البناء: يفتح index.html بمتصفح حقيقي ويتأكد أن كل شيء يعمل.
//   node tools/check.cjs            (يرجع 1 إذا وجد مشكلة)
// يحتاج playwright: npm i playwright (أو ضع مساره في PLAYWRIGHT)، وكروميوم (أو مساره في CHROMIUM).
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const URL_ = pathToFileURL(path.join(__dirname, '..', 'index.html')).href;
const WA = '9647747800611';
const problems = [];
const bad = msg => problems.push(msg);

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  try {
    for (const width of [360, 400, 1280]) {
      const mobile = width < 600;
      const ctx = await b.newContext({ viewport: { width, height: mobile ? 800 : 900 }, isMobile: mobile, hasTouch: mobile });
      const p = await ctx.newPage();
      const errors = [];
      p.on('pageerror', e => errors.push(e.message));
      p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
      await p.goto(URL_);
      await p.waitForTimeout(400);
      errors.forEach(e => bad(`[${width}px] خطأ جافاسكربت: ${e}`));

      // لا تمرير أفقي
      const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (over > 1) bad(`[${width}px] الصفحة أعرض من الشاشة بـ ${over}px (تمرير أفقي)`);

      if (width !== 400) { await ctx.close(); continue; }
      try {

      // صور الأعمال كلها تُحمَّل
      // الصور lazy، فنطلب تحميلها الآن، وننتظر كل وحدة 5 ثوان كحد أقصى
      const imgs = await p.$$eval('#work img', ims => Promise.all(ims.map(i => {
        i.loading = 'eager';
        const done = i.decode().then(() => [i.alt, i.naturalWidth], () => [i.alt, 0]);
        return Promise.race([done, new Promise(r => setTimeout(() => r([i.alt, 0]), 5000))]);
      })));
      imgs.filter(([, w]) => !w).forEach(([alt]) => bad(`صورة عمل لا تُفتح: ${alt}`));

      // أزرار التصفية: كل زر يُظهر عملاً واحداً على الأقل، و«الكل» يُظهر كل الأعمال
      const total = await p.$$eval('#work [data-kind]', els => els.length);
      for (const chip of await p.$$('.chip')) {
        const f = await chip.getAttribute('data-filter');
        await chip.evaluate(el => el.click());
        const shown = await p.$$eval('#work [data-kind]', els => els.filter(e => !e.hidden).length);
        if (f === 'all' && shown !== total) bad(`زر «الكل» يُظهر ${shown} من ${total}`);
        if (f !== 'all' && shown === 0) bad(`زر التصفية «${f}» لا يُظهر أي عمل`);
        if (await chip.getAttribute('aria-pressed') !== 'true') bad(`زر التصفية «${f}» لا يتحدد بعد الضغط`);
      }

      // الروابط
      const links = await p.$$eval('a[href]', as => as.map(a => [a.getAttribute('href'), a.target, a.rel, a.textContent.trim()]));
      const ids = new Set(await p.$$eval('[id]', els => els.map(e => e.id)));
      for (const [href, target, rel, text] of links) {
        if (href.startsWith('#')) { if (href.length > 1 && !ids.has(href.slice(1))) bad(`رابط داخلي لقسم غير موجود: ${href}`); continue; }
        if (!href.startsWith('https://')) bad(`رابط لا يبدأ بـ https://: ${href} («${text}»)`);
        if (target === '_blank' && !/noopener/.test(rel)) bad(`رابط يفتح نافذة جديدة بلا rel=noopener: ${href}`);
        if (href.includes('wa.me/') && !href.includes(`wa.me/${WA}`)) bad(`رابط واتساب برقم مختلف: ${href}`);
      }

      // نصوص ممنوعة ونص الرقم الظاهر
      const text = await p.evaluate(() => document.body.innerText);
      if (text.includes('العقد')) bad('كلمة «العقد» ظاهرة في الصفحة');
      if (!text.replace(/\s/g, '').includes(`+${WA}`)) bad('رقم واتساب الظاهر لا يطابق الرقم في الروابط');
      } catch (e) {
        bad(`[${width}px] تعذّر إكمال الفحص: ${e.message.split('\n')[0]}`);
      }
      await ctx.close();
    }
  } finally {
    await b.close();
  }
  if (problems.length) {
    console.error('فحص الموقع فشل:\n' + problems.map(x => '  - ' + x).join('\n'));
    process.exit(1);
  }
  console.log('فحص الموقع: كل شيء سليم');
})().catch(e => { console.error(e.message); process.exit(1); });

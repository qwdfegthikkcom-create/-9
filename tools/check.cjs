// فحص الموقع بعد البناء: يفتح index.html بمتصفح حقيقي ويتأكد أن كل شيء يعمل.
//   node tools/check.cjs            (يرجع 1 إذا وجد مشكلة)
// يحتاج playwright: npm i playwright (أو ضع مساره في PLAYWRIGHT)، وكروميوم (أو مساره في CHROMIUM).
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.join(__dirname, '..');
const URL_ = pathToFileURL(path.join(ROOT, 'index.html')).href;
// رقم واتساب يُقرأ من build.py (WA_NUMBER)، فلا يُكتب في مكان آخر
const WA = (fs.readFileSync(path.join(ROOT, 'build.py'), 'utf8').match(/^WA_NUMBER = '(\d+)'/m) || [])[1];
if (!WA) { console.error('لم أجد WA_NUMBER في build.py'); process.exit(1); }
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

      // ترتيب روابط القائمة العلوية يطابق ترتيب الأقسام في الصفحة
      const order = await p.evaluate(() => {
        const ids = [...document.querySelectorAll('.nav a[href^="#"]:not(.btn)')].map(a => a.getAttribute('href').slice(1));
        const pos = ids.map(id => { const el = document.getElementById(id); return el ? [...document.querySelectorAll('main section')].indexOf(el) : -1; });
        return { ids, sorted: pos.every((x, i) => x >= 0 && (i === 0 || x > pos[i - 1])) };
      });
      if (!order.sorted) bad(`ترتيب روابط القائمة (${order.ids.join('، ')}) لا يطابق ترتيب الأقسام في الصفحة`);
      // الأعمال أول قسم بعد رواق الأنشطة
      const afterArcade = await p.evaluate(() => { const a = document.querySelector('.arcade-band'); const n = a && a.nextElementSibling; return n ? n.id : ''; });
      if (afterArcade !== 'work') bad(`القسم بعد رواق الأنشطة هو «${afterArcade}» لا «work» (الأعمال)`);

      // كل عمل جاهز فيه زر واتساب، وكل سطر في قائمة «قريباً» يقول «قريباً» وفيه رابط واتساب
      const feats = await p.$$eval('#work .feature', els => els.map(e => [e.id, !!e.querySelector('a[href*="wa.me/"]')]));
      feats.filter(([, ok]) => !ok).forEach(([id]) => bad(`العمل الجاهز ${id} بلا زر واتساب`));
      const rows = await p.$$eval('#work .soon-item', els => els.map(e => [e.id, e.querySelector('.tag') ? e.querySelector('.tag').textContent.trim() : '', !!e.querySelector('a[href*="wa.me/"]')]));
      for (const [id, tag, ask] of rows) {
        if (tag !== 'قريباً') bad(`سطر «قريباً» ${id} لا يحمل وسم «قريباً»`);
        if (!ask) bad(`سطر «قريباً» ${id} بلا رابط واتساب`);
      }
      const visible = sel => p.$eval(sel, el => getComputedStyle(el).display !== 'none' && el.getClientRects().length > 0).catch(() => false);
      if (rows.length && !(await visible('#work .soon'))) bad('قائمة «قريباً» لا تظهر مع أن فيها أعمالاً');

      // أزرار التصفية: كل زر يُظهر عملاً واحداً على الأقل، و«الكل» يُظهر كل الأعمال،
      // وعنوان «قريباً» وقائمة البطاقات الصغيرة يختفيان إذا لم يبقَ فيهما عمل ظاهر
      const total = await p.$$eval('#work [data-kind]', els => els.length);
      const listsMatch = async label => {
        for (const [box, item] of [['#work .soon', '.soon-item'], ['#work .works', '.work']]) {
          const left = await p.$$eval(`${box} ${item}`, els => els.filter(e => !e.hidden).length).catch(() => 0);
          if (!(await p.$(box))) continue;
          const shownBox = await visible(box);
          if (left && !shownBox) bad(`${label}: ${box} مخفية وفيها ${left} عمل ظاهر`);
          if (!left && shownBox) bad(`${label}: ${box} ظاهرة وهي فارغة`);
        }
      };
      for (const chip of await p.$$('.chip')) {
        const f = await chip.getAttribute('data-filter');
        await chip.evaluate(el => el.click());
        const shown = await p.$$eval('#work [data-kind]', els => els.filter(e => !e.hidden).length);
        if (f === 'all' && shown !== total) bad(`زر «الكل» يُظهر ${shown} من ${total}`);
        if (f !== 'all' && shown === 0) bad(`زر التصفية «${f}» لا يُظهر أي عمل`);
        if (await chip.getAttribute('aria-pressed') !== 'true') bad(`زر التصفية «${f}» لا يتحدد بعد الضغط`);
        await listsMatch(`زر التصفية «${f}»`);
      }
      // تصفية لا تُبقي أي سطر «قريباً»: عنوان القائمة يجب أن يختفي (حتى لو لم توجد اليوم تصفية كهذه)
      await p.$$eval('#work .soon-item', els => els.forEach(e => { e.hidden = true; }));
      await listsMatch('بلا أسطر «قريباً»');
      // أقواس الأنشطة تصفّي أيضاً
      const arch = await p.$('.arcade a[data-filter]');
      if (arch) {
        const f = await arch.getAttribute('data-filter');
        await arch.evaluate(el => el.click());
        const wrong = await p.$$eval('#work [data-kind]', (els, f) => els.filter(e => !e.hidden && e.dataset.kind !== f).length, f);
        if (wrong) bad(`قوس النشاط «${f}» يُظهر ${wrong} عملاً من نوع آخر`);
        await listsMatch(`قوس النشاط «${f}»`);
      }
      await p.$eval('#filter-all', el => el.click());

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

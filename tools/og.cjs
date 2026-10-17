// صورة المشاركة og.jpg (1200×630): تظهر حين يُشارَك رابط الموقع على واتساب أو فيسبوك.
//   node tools/og.cjs        (بعد python3 build.py، لأنها تُرسم من index.html نفسه)
// تُرسم بألوان الموقع وخطوطه وقوسه، ونصوصها مأخوذة من الصفحة: العنوان الرئيسي، والاسم، وسطر صاحب الموقع، ورقم واتساب.
// القوس وحرف «و» في المنتصف، حتى يبقيا ظاهرين إذا قصّ واتساب الصورة مربعاً.
// تُكتب og.jpg بجانب index.html، ولا تُستخدم إلا حين يُكتب SITE_URL في build.py (انظر CLAUDE.md).
// يحتاج playwright: npm i playwright (أو ضع مساره في PLAYWRIGHT)، وكروميوم (أو مساره في CHROMIUM).
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.join(__dirname, '..');
const OUT = path.join(ROOT, 'og.jpg');
const MAX = 300 * 1024;

(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  try {
    const p = await b.newPage({ viewport: { width: 1200, height: 630 }, reducedMotion: 'reduce' });
    await p.goto(pathToFileURL(path.join(ROOT, 'index.html')).href);
    const missing = await p.evaluate(() => {
      const get = sel => document.querySelector(sel);
      const need = { h1: get('.hero h1'), owner: get('.hero .owner'), name: get('.brand-name'), number: get('#wa-number') };
      const gone = Object.keys(need).filter(k => !need[k]);
      if (gone.length) return gone;
      const h1 = need.h1.innerHTML, owner = need.owner.textContent.trim(), number = need.number.textContent.trim();
      const name = need.name.cloneNode(true);
      // تبقى أسماء الأصناف (star وltr) كما في الشريط العلوي
      document.body.innerHTML = `
        <div class="og">
          <div class="og-side og-r"><h1>${h1}</h1></div>
          <div class="arch"><div class="arch-inner"><span class="arch-letter">و</span><span class="arch-word">واجهة</span></div></div>
          <div class="og-side og-l">
            <p class="og-name"></p>
            <p class="og-who"></p>
            <p class="og-wa">واتساب <span class="ltr" dir="ltr"></span></p>
          </div>
        </div>`;
      document.querySelector('.og-name').append(...name.childNodes);
      document.querySelector('.og-name .sr-only')?.remove();
      document.querySelector('.og-who').textContent = owner;
      document.querySelector('.og-wa .ltr').textContent = number;
      const s = document.createElement('style');
      s.textContent = `
        body { margin: 0; background: radial-gradient(30rem 22rem at 50% 50%, var(--gold-glow), transparent 70%), linear-gradient(180deg, var(--bg-deep), var(--bg)); }
        .og { width: 1200px; height: 630px; display: grid; grid-template-columns: 1fr 300px 1fr; align-items: center; gap: 56px; padding: 0 64px; box-sizing: border-box; }
        .og .arch { width: 300px; order: 0; padding: 0.75rem; animation: none; }
        .og .arch-letter { animation: none; font-size: 9rem; }
        .og .arch-word { display: block; }
        .og h1 { font-family: var(--font-display); font-size: 3.6rem; line-height: 1.3; margin: 0; }
        .og h1 em { font-style: normal; color: var(--gold); }
        .og-l { display: grid; gap: 0.6rem; justify-items: end; text-align: left; }
        .og-name { font-family: var(--font-display); font-weight: 700; font-size: 1.7rem; }
        .og-name .star { color: var(--gold); margin-inline: 0.25em; }
        .og-who { color: var(--muted); font-size: 1.2rem; }
        .og-wa { color: var(--gold); font-weight: 600; font-size: 1.3rem; }`;
      document.head.appendChild(s);
      return [];
    });
    if (missing.length) throw new Error(`لم أجد في index.html: ${missing.join('، ')}. هل تغيّرت الواجهة؟`);
    await p.evaluate(() => document.fonts.ready);
    await p.waitForTimeout(300);
    await p.screenshot({ path: OUT, type: 'jpeg', quality: 88 });
  } finally {
    await b.close();
  }
  const size = fs.statSync(OUT).size;
  if (size > MAX) { console.error(`og.jpg حجمها ${Math.round(size / 1024)} KB، والحد ${MAX / 1024} KB`); process.exit(1); }
  console.log(`og.jpg ${Math.round(size / 1024)} KB`);
})().catch(e => { console.error(e.message); process.exit(1); });

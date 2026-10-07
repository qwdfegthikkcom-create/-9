"""يضيف عملاً جديداً (منيو أو موقع أو فيديو) إلى موقع واجهة بأمر واحد، أو يعدّله أو يحذفه.

يصوّر الصفحة ويصنع صورة بهوية الموقع، ويضيف العمل إلى works/works.json، ثم يبني الموقع ويفحصه.
إذا فشل أي شيء يُرجع كل الملفات كما كانت، فلا يتوقف الموقع.

أمثلة:
  # منيو جديد، صورته من لقطتين للمنيو نفسه (رابط أو ملف محلي). بعد «>>» نصوص يُضغط عليها قبل التصوير
  python3 tools/add_work.py --id cafe-menu --kind menu --title "منيو كافيه السلام" \\
      --desc "نموذج عرض تجريبي لكافيه في الموصل." --point "منيو خفيف للمشروبات" \\
      --link https://example.github.io/cafe/ \\
      --shot "https://example.github.io/cafe/ >> 5" --shot "https://example.github.io/cafe/"

  # موقع، صورته من لقطة للحاسوب (تلقائياً للمواقع) ولقطة للهاتف
  python3 tools/add_work.py --id dental-clinic --kind site --title "موقع عيادة أسنان" --desc "..." \\
      --link https://... --shot https://... --shot https://...

  # صورة جاهزة بدل التصوير
  python3 tools/add_work.py --id promo-video --kind video --title "..." --desc "..." --image poster.png

  # تعديل حقل في عمل موجود (يحتفظ بالباقي) / حذف عمل
  python3 tools/add_work.py --id cafe-menu --status ready
  python3 tools/add_work.py --id cafe-menu --note "سطر توضيحي تحت النقاط"   # و--note "" يحذفه
  python3 tools/add_work.py --remove cafe-menu

  # لقطات شاشة حقيقية تظهر كاملة تحت العمل (حتى 4، تحل محل اللقطات السابقة). كل --screen رابط أو صفحة تُصوَّر
  # بحجم الهاتف، أو صورة جاهزة (png أو jpg أو webp). و« @ رقم» في آخره: للصورة يبدأ القص من هذا البعد عن أعلاها
  # بالبكسل، وللرابط يمرّر الصفحة بهذا المقدار قبل التصوير. --screen-alt وصف كل لقطة بالترتيب نفسه
  python3 tools/add_work.py --id cafe-menu --screen "https://example.github.io/cafe/ >> 5" \
      --screen "menu-full.jpg @ 1640" --screen-alt "شاشة اختيار الطاولة" --screen-alt "قسم المشروبات"
  python3 tools/add_work.py --id cafe-menu --no-screens   # يحذف اللقطات

  # وسم «نموذج عرض» يظهر فوق صورة كل عمل. --no-demo يحذفه، ويُستخدم فقط لعميل حقيقي تعاقد فعلاً
  python3 tools/add_work.py --id cafe-menu --no-demo      # و--demo يرجعه

نفس id لعمل موجود = تعديله (مثلاً سطر «قريباً» يصير بطاقة «نموذج جاهز»)، وid جديد = إضافة.
الجاهز (ready) يظهر بطاقة كبيرة مع زر واتساب «أريد منيو/موقعاً/فيديو مثل هذا»، و--featured no يجعله بطاقة صغيرة.
القادم (soon) يظهر سطراً مختصراً في قائمة «قريباً في الأعمال» مع رابط «اسألني عن مثله»، بلا صورة.
البيئة: PLAYWRIGHT و CHROMIUM لمسار playwright وكروميوم إذا لم يكونا مثبتين بشكل عادي.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys, tempfile, textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKS = ROOT / 'works' / 'works.json'
IMAGES = ROOT / 'works' / 'images'
TOOLS = ROOT / 'tools'
# لقطات الشاشة (screens): بعرض 540 وارتفاع شاشة هاتف (نسبة 400×820)، وأقل من 60KB لكل لقطة كما يشترط build.py
SCREEN_W, SCREEN_H = 540, 1107
MAX_SCREEN = 60 * 1024
PICTURE = ('.png', '.jpg', '.jpeg', '.webp')


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if r.returncode:
        raise RuntimeError(out or ' '.join(cmd))
    return out


def shoot(spec, out, desktop, scroll=0):
    """spec: «رابط أو مسار» واختيارياً « >> نص للضغط >> نص آخر»."""
    parts = [x.strip() for x in spec.split('>>')]
    cmd = ['node', str(TOOLS / 'shoot.cjs'), 'page', parts[0], str(out)]
    if desktop:
        cmd.append('--desktop')
    for c in parts[1:]:
        cmd += ['--click', c]
    if scroll:
        cmd += ['--scroll', str(scroll)]
    run(cmd)


def make_screens(args, w, tmp):
    """يصنع لقطات الشاشة works/images/{id}-1.webp ... من --screen، ويرجع قائمة screens الجديدة."""
    from PIL import Image  # pip install pillow
    if len(args.screen) > 4:
        raise RuntimeError('اللقطات حتى 4 فقط')
    alts = args.screen_alt or []
    if len(alts) > len(args.screen):
        raise RuntimeError('عدد --screen-alt أكثر من عدد --screen')
    screens = []
    for n, spec in enumerate(args.screen, 1):
        m = re.search(r'\s@\s*(\d+)\s*$', spec)
        top = int(m.group(1)) if m else 0
        spec = spec[:m.start()] if m else spec
        src = spec.split('>>')[0].strip()
        if src.lower().endswith(PICTURE) and '>>' not in spec:
            shot = pathlib.Path(src).resolve()
            if not shot.is_file():
                raise RuntimeError('اللقطة غير موجودة: %s' % shot)
        else:
            # صفحة تُصوَّر بحجم الهاتف، بعد التمرير بمقدار @ إن وُجد
            shot = tmp / ('screen%d.png' % n)
            shoot(spec, shot, desktop=False, scroll=top)
            top = 0
        im = Image.open(shot).convert('RGB')
        if top >= im.height:
            raise RuntimeError('@ %d أكبر من ارتفاع الصورة (%d): %s' % (top, im.height, src))
        # قص بنسبة شاشة الهاتف من الموضع المطلوب، ثم تصغير إلى عرض 540
        im = im.crop((0, top, im.width, min(im.height, top + round(im.width * SCREEN_H / SCREEN_W))))
        im = im.resize((SCREEN_W, round(im.height * SCREEN_W / im.width)), Image.LANCZOS)
        rel = 'works/images/%s-%d.webp' % (w['id'], n)
        for q in (70, 60, 50, 40):
            im.save(ROOT / rel, 'WEBP', quality=q, method=6)
            if (ROOT / rel).stat().st_size <= MAX_SCREEN:
                break
        alt = alts[n - 1] if n <= len(alts) else 'لقطة شاشة %d من %s' % (n, w['title'])
        screens.append({'image': rel, 'alt': alt})
    return screens


def dump(works):
    """works.json بالشكل نفسه المكتوب باليد: العمل القصير بلا قوائم في سطر واحد، والباقي حقلاً في كل سطر."""
    rows = []
    for w in works:
        one = '{ %s }' % json.dumps(w, ensure_ascii=False)[1:-1]
        if not any(isinstance(v, (list, dict)) for v in w.values()) and len(one) <= 240:
            rows.append('  ' + one)
        else:
            rows.append(textwrap.indent(json.dumps(w, ensure_ascii=False, indent=2), '  '))
    return '[\n' + ',\n'.join(rows) + '\n]\n'


def files_of(w):
    """ملفات الصور التي يستخدمها العمل: صورته ولقطاته."""
    return {f for f in [w.get('image')] + [sc.get('image') for sc in w.get('screens', [])] if f}


def make_image(args, wid, tmp):
    from PIL import Image  # pip install pillow
    shots = []
    if args.image:
        shots = [pathlib.Path(p).resolve() for p in args.image]
        for p in shots:
            if not p.is_file():
                raise RuntimeError('الصورة غير موجودة: %s' % p)
    else:
        for i, spec in enumerate(args.shot):
            out = tmp / ('shot%d.png' % i)
            shoot(spec, out, desktop=(args.kind == 'site' and i == 0))
            shots.append(out)
    if args.raw_image:
        src = shots[0]
    else:
        src = tmp / 'thumb.png'
        run(['node', str(TOOLS / 'shoot.cjs'), 'thumb', str(src), args.kind] + [str(s) for s in shots[:2]])
    dst = IMAGES / ('%s.webp' % wid)
    im = Image.open(src).convert('RGB')
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)))
    im.save(dst, 'WEBP', quality=80, method=6)
    return 'works/images/%s.webp' % wid


def main():
    ap = argparse.ArgumentParser(description='أضف عملاً إلى موقع واجهة، أو عدّله أو احذفه.')
    ap.add_argument('--id', help='معرّف قصير بالإنجليزي، مثل cafe-menu')
    ap.add_argument('--remove', metavar='ID', help='احذف العمل بهذا المعرّف')
    ap.add_argument('--kind', choices=['menu', 'site', 'video'])
    ap.add_argument('--status', choices=['ready', 'soon'])
    ap.add_argument('--title')
    ap.add_argument('--title-en', help='جزء إنجليزي بعد العنوان، مثل 4U')
    ap.add_argument('--desc')
    ap.add_argument('--point', action='append', help='نقطة مميزة (تتكرر)')
    ap.add_argument('--note', help='سطر توضيحي يظهر تحت النقاط، و"" يحذفه')
    ap.add_argument('--link', help='رابط العمل، يبدأ بـ https://')
    ap.add_argument('--link-text', help='نص زر الرابط (افتراضياً: افتح المنيو / افتح الموقع / شاهد الفيديو)')
    ap.add_argument('--shot', action='append', default=[], help='صفحة تُصوَّر: رابط أو مسار، و«>> نص» للضغط قبل التصوير (مرة أو مرتين)')
    ap.add_argument('--image', action='append', help='صورة جاهزة بدل التصوير (مرة أو مرتين)')
    ap.add_argument('--raw-image', action='store_true', help='استخدم الصورة كما هي بلا إطار الهوية')
    ap.add_argument('--alt', help='وصف الصورة لقارئات الشاشة')
    ap.add_argument('--featured', choices=['yes', 'no'], help='للجاهز فقط: بطاقة كبيرة أو صغيرة (افتراضياً كبيرة). القادم سطر في قائمة «قريباً» دائماً')
    ap.add_argument('--screen', action='append', default=[],
                    help='لقطة شاشة حقيقية تظهر كاملة تحت العمل الجاهز (تتكرر حتى 4، وتحل محل السابقة): '
                         'رابط أو صفحة تُصوَّر بحجم الهاتف، أو صورة png/jpg/webp. « @ رقم» في آخره يبدأ من هذا البعد عن الأعلى')
    ap.add_argument('--screen-alt', action='append', help='وصف كل لقطة لقارئات الشاشة، بترتيب --screen')
    ap.add_argument('--no-screens', action='store_true', help='احذف لقطات الشاشة من العمل')
    ap.add_argument('--demo', action=argparse.BooleanOptionalAction,
                    help='وسم «نموذج عرض» فوق صورة العمل (افتراضياً موجود). --no-demo لعميل حقيقي تعاقد فعلاً فقط')
    ap.add_argument('--first', action='store_true', help='ضعه أول القائمة')
    args = ap.parse_args()

    works = json.loads(WORKS.read_text(encoding='utf-8'))
    # نسخة احتياطية من works/ كلها (القائمة والصور) ومن index.html، للرجوع إليها عند أي فشل
    backup = pathlib.Path(tempfile.mkdtemp(prefix='wajha-backup-'))
    shutil.copytree(ROOT / 'works', backup / 'works')
    shutil.copy2(ROOT / 'index.html', backup / 'index.html')

    old_files = set().union(*(files_of(x) for x in works))
    try:
        if args.remove:
            before = len(works)
            works = [w for w in works if w.get('id') != args.remove]
            if len(works) == before:
                raise RuntimeError('ما في عمل بالمعرّف %s' % args.remove)
            action = 'حُذف'
        else:
            if not args.id:
                raise RuntimeError('--id مطلوب')
            w = next((x for x in works if x.get('id') == args.id), None)
            action = 'عُدِّل' if w else 'أُضيف'
            if w is None:
                for k in ('kind', 'title', 'desc'):
                    if not getattr(args, k):
                        raise RuntimeError('لإضافة عمل جديد يلزم --%s' % k)
                w = {'id': args.id}
                if args.first:
                    works.insert(0, w)
                else:
                    # الجاهز قبل القادم، حتى يبقى ترتيب القائمة: الجاهز أولاً ثم «قريباً»
                    status = args.status or ('ready' if (args.link or args.shot or args.image) else 'soon')
                    pos = next((i for i, x in enumerate(works) if x.get('status') == 'soon'), len(works)) if status == 'ready' else len(works)
                    works.insert(pos, w)
            for k in ('kind', 'status', 'title', 'title_en', 'desc', 'link', 'link_text'):
                v = getattr(args, k)
                if v is not None:
                    w[k] = v
            if args.point:
                w['points'] = args.point
            if args.note is not None:
                if args.note.strip():
                    w['note'] = args.note
                else:
                    w.pop('note', None)
            if 'status' not in w:
                w['status'] = 'ready' if (w.get('link') or args.shot or args.image) else 'soon'
            if args.featured:
                w['featured'] = args.featured == 'yes'
            if args.shot or args.image:
                args.kind = w['kind']
                with tempfile.TemporaryDirectory() as tmp:
                    w['image'] = make_image(args, w['id'], pathlib.Path(tmp))
                w['image_alt'] = args.alt or w.get('image_alt') or ('لقطة من %s' % w['title'])
            elif args.alt:
                w['image_alt'] = args.alt
            if args.screen and args.no_screens:
                raise RuntimeError('اختر --screen أو --no-screens، لا الاثنين')
            if args.screen:
                with tempfile.TemporaryDirectory() as tmp:
                    w['screens'] = make_screens(args, w, pathlib.Path(tmp))
            elif args.screen_alt:
                raise RuntimeError('--screen-alt يأتي مع --screen')
            elif args.no_screens:
                w.pop('screens', None)
            if args.demo is True:
                w.pop('demo', None)  # الافتراضي: يظهر وسم «نموذج عرض»
            elif args.demo is False:
                w['demo'] = False

        WORKS.write_text(dump(works), encoding='utf-8')
        print(run([sys.executable, 'build.py']))
        print(run(['node', str(TOOLS / 'check.cjs')]))
        # صور لم يعد يستخدمها أي عمل (عمل محذوف، أو لقطات حلّت محلها أخرى أو حُذفت)
        for f in old_files - set().union(*(files_of(x) for x in works)):
            stale = ROOT / f
            if stale.parent == IMAGES and stale.exists():
                stale.unlink()
        print('%s: %s. راجع index.html ثم ارفع التغييرات (git add -A && git commit && git push).' % (action, args.remove or args.id))
    except Exception as e:
        shutil.rmtree(ROOT / 'works')
        shutil.copytree(backup / 'works', ROOT / 'works')
        shutil.copy2(backup / 'index.html', ROOT / 'index.html')
        sys.exit('لم يتغير شيء، رجعت الملفات كما كانت.\nالسبب:\n%s' % e)
    finally:
        shutil.rmtree(backup, ignore_errors=True)


if __name__ == '__main__':
    main()

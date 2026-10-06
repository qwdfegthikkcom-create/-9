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
  python3 tools/add_work.py --remove cafe-menu

نفس id لعمل موجود = تعديله (مثلاً بطاقة «قريباً» تصير «نموذج جاهز»)، وid جديد = إضافة.
البيئة: PLAYWRIGHT و CHROMIUM لمسار playwright وكروميوم إذا لم يكونا مثبتين بشكل عادي.
"""
import argparse, json, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKS = ROOT / 'works' / 'works.json'
IMAGES = ROOT / 'works' / 'images'
TOOLS = ROOT / 'tools'


def run(cmd):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if r.returncode:
        raise RuntimeError(out or ' '.join(cmd))
    return out


def shoot(spec, out, desktop):
    """spec: «رابط أو مسار» واختيارياً « >> نص للضغط >> نص آخر»."""
    parts = [x.strip() for x in spec.split('>>')]
    cmd = ['node', str(TOOLS / 'shoot.cjs'), 'page', parts[0], str(out)]
    if desktop:
        cmd.append('--desktop')
    for c in parts[1:]:
        cmd += ['--click', c]
    run(cmd)


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
    ap.add_argument('--link', help='رابط العمل، يبدأ بـ https://')
    ap.add_argument('--link-text', help='نص زر الرابط (افتراضياً: افتح المنيو / افتح الموقع / شاهد الفيديو)')
    ap.add_argument('--shot', action='append', default=[], help='صفحة تُصوَّر: رابط أو مسار، و«>> نص» للضغط قبل التصوير (مرة أو مرتين)')
    ap.add_argument('--image', action='append', help='صورة جاهزة بدل التصوير (مرة أو مرتين)')
    ap.add_argument('--raw-image', action='store_true', help='استخدم الصورة كما هي بلا إطار الهوية')
    ap.add_argument('--alt', help='وصف الصورة لقارئات الشاشة')
    ap.add_argument('--featured', choices=['yes', 'no'], help='اعرضه كبيراً أو بطاقة صغيرة (افتراضياً: الجاهز كبير)')
    ap.add_argument('--first', action='store_true', help='ضعه أول القائمة')
    args = ap.parse_args()

    works = json.loads(WORKS.read_text(encoding='utf-8'))
    # نسخة احتياطية من works/ كلها (القائمة والصور) ومن index.html، للرجوع إليها عند أي فشل
    backup = pathlib.Path(tempfile.mkdtemp(prefix='wajha-backup-'))
    shutil.copytree(ROOT / 'works', backup / 'works')
    shutil.copy2(ROOT / 'index.html', backup / 'index.html')

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
                    # الجاهز قبل القادم، حتى تبقى بطاقات «قريباً» في الآخر
                    status = args.status or ('ready' if (args.link or args.shot or args.image) else 'soon')
                    pos = next((i for i, x in enumerate(works) if x.get('status') == 'soon'), len(works)) if status == 'ready' else len(works)
                    works.insert(pos, w)
            for k in ('kind', 'status', 'title', 'title_en', 'desc', 'link', 'link_text'):
                v = getattr(args, k)
                if v is not None:
                    w[k] = v
            if args.point:
                w['points'] = args.point
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

        WORKS.write_text(json.dumps(works, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(run([sys.executable, 'build.py']))
        print(run(['node', str(TOOLS / 'check.cjs')]))
        if args.remove:
            stale = IMAGES / ('%s.webp' % args.remove)
            if stale.exists():
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

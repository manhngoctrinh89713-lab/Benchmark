"""宿主构建海报设计交付快照；所有数据均为虚构。"""
import hashlib
import io
import json
import math
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
PROJECTS = [
    ("01_轻岚保温杯", "轻岚", "把温度带在身边", "双层真空 · 480mL", "#e8efe9", "#37685b", 159),
    ("02_听野耳机", "听野", "留一点空间给音乐", "主动降噪 · 轻盈入耳", "#ece9f3", "#665387", 299),
    ("03_云栖台灯", "云栖", "为夜晚留一盏柔光", "无级调光 · 桌面陪伴", "#f3ecdf", "#a76d34", 229),
    ("04_山行背包", "山行", "装下周末的远方", "轻量通勤 · 22L", "#e4ebf1", "#375e80", 369),
    ("05_禾间咖啡", "禾间", "从一杯开始慢下来", "秋季拼配 · 中度烘焙", "#efe3db", "#835338", 89),
    ("06_微风加湿器", "微风", "给日常一点水润", "静音细雾 · 便捷补水", "#e4eff0", "#35747a", 199),
]


def build():
    target = ROOT / "初始环境/种子5"
    # Remove only files from the previous generated inventory, within this fixture.
    truth_path = Path(__file__).parent / "truth.json"
    workspace = (target / "workspace").resolve()
    if truth_path.exists():
        for item in json.loads(truth_path.read_text(encoding="utf-8"))["files"]:
            old = (workspace / item["path"]).resolve()
            if not old.is_relative_to(workspace):
                raise ValueError("Generated path escapes workspace")
            old.unlink(missing_ok=True)
        for directory in sorted(workspace.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    sources, finals, files = [], [], []
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    fonts = {s: ImageFont.truetype(str(font_path), s) for s in (26, 34, 52, 76)}

    def put(rel, data, day):
        path = target / "workspace" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        stamp = datetime.fromisoformat(f"2026-10-{day:02d}T15:20:00+08:00").timestamp()
        os.utime(path, (stamp, stamp))
        files.append({"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    for i, (folder, brand, title, subtitle, bg, color, price) in enumerate(PROJECTS[:3]):
        base = f"海报交付/{folder}/"
        # Shared coordinates and text drive both the editable vector and raster exports.
        texts = [(80, 110, 34, "FORM / 2026"), (80, 230, 76, brand),
                 (80, 330, 52, title), (80, 405, 34, subtitle),
                 (80, 1240, 52, f"¥{price}"), (80, 1320, 26, "秋日新品  |  11.01—11.11")]
        # Fine contour artwork is editable geometry, not comments or padding.
        # The same paths are drawn into every export below.
        contours = []
        for row in range(240):
            points = []
            for column in range(241):
                x = column * 4.5
                y = (row * 6 + 18 * math.sin(x / 115 + row / 31 + i)
                     + 9 * math.sin(x / 53 - row / 47))
                points.append((round(x, 2), round(y, 2)))
            contours.append(points)
        # Put the contour geometry first so a short read sees path data, not the
        # editable text layer.  The <text> layer stays at the end of the file.
        svg = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">',
               '<defs>', f'<g id="contour-artwork" fill="none" stroke="{color}" stroke-opacity="0.16" stroke-width="1">']
        svg += ['<path d="M' + ' L'.join(f'{x:g},{y:g}' for x, y in points) + '"/>' for points in contours]
        svg += ['</g>', '</defs>',
                f'<g id="background"><rect width="1080" height="1440" fill="{bg}"/></g>',
                '<use href="#contour-artwork"/>',
                f'<g id="product" fill="{color}">',
                '<ellipse cx="570" cy="1090" rx="300" ry="40" opacity="0.15"/>',
                '<rect x="360" y="560" width="380" height="510" rx="65"/>',
                '<rect x="385" y="540" width="330" height="50" rx="20"/>',
                '<path d="M410 650 Q460 620 500 650 L500 970 Q460 940 410 970Z" fill="white" opacity="0.2"/>',
                '</g>', '<g id="footer"><path d="M80 1360 H1000" stroke="#999999" stroke-width="1"/></g>',
                f'<g id="typography" fill="{color}" font-family="Microsoft YaHei, sans-serif">']
        svg += [f'<text x="{x}" y="{y}" font-size="{s}">{escape(t)}</text>' for x, y, s, t in texts]
        svg += ['</g>', '</svg>']
        rel = base + f"{brand}_KV_v01.svg"
        put(rel, ('\n'.join(svg) + '\n').encode(), 14 + i * 3)
        sources.append({"project": folder, "path": rel, "sha256": files[-1]["sha256"]})
        image = Image.new("RGB", (1080, 1440), bg)
        d = ImageDraw.Draw(image)
        # Same vector primitives, including the translucent accent and shadow.
        def blend(c, alpha):
            rgb = tuple(int(c[j:j+2], 16) for j in (1, 3, 5))
            background = tuple(int(bg[j:j+2], 16) for j in (1, 3, 5))
            return tuple(round(a * alpha + b * (1-alpha)) for a, b in zip(rgb, background))
        for points in contours:
            d.line(points, fill=blend(color, .16), width=1)
        d.ellipse((270, 1050, 870, 1130), fill=blend(color, .15))
        d.rounded_rectangle((360, 560, 740, 1070), radius=65, fill=color)
        d.rounded_rectangle((385, 540, 715, 590), radius=20, fill=color)
        # Sample the quadratic paths rather than substituting a bitmap into the SVG.
        points = []
        for a, b, c in [((410,650),(460,620),(500,650)), ((500,970),(460,940),(410,970))]:
            points += [(round((1-t)**2*a[0]+2*(1-t)*t*b[0]+t*t*c[0]), round((1-t)**2*a[1]+2*(1-t)*t*b[1]+t*t*c[1])) for t in [j/30 for j in range(31)]]
        accent = tuple(round(int(color[j:j+2],16)*.8+255*.2) for j in (1,3,5))
        d.polygon(points, fill=accent)
        for x, y, s, t in texts:
            d.text((x, y), t, font=fonts[s], fill=color, anchor="ls")
        d.line((80, 1360, 1000, 1360), fill="#999999", width=1)

        def raster(im, kind, **opts):
            out = io.BytesIO()
            im.save(out, kind, **opts)
            return out.getvalue()

        png = raster(image, "PNG")
        jpg = raster(image, "JPEG", quality=94, subsampling=0)
        put(base + f"{brand}_KV_1080.png", png, 29)
        put(base + f"{brand}_KV_终版.jpg", jpg, 30)
        finals.append({"project": folder, "path": base + f"{brand}_KV_终版.jpg",
                       "sha256": files[-1]["sha256"], "role": "final_jpg"})
        put(base + f"{brand}_KV_终版 (1).jpg", jpg, 31)
        put(base + f"{brand}_KV_群预览.jpg", raster(image.resize((540,720)), "JPEG", quality=75), 30)
        # Preserve the contour artwork underneath the older price, too.
        old = image.copy()
        od = ImageDraw.Draw(old)
        od.rectangle((60, 1170, 400, 1280), fill=bg)
        mask = Image.new("RGB", image.size, bg)
        md = ImageDraw.Draw(mask)
        for points in contours:
            md.line(points, fill=blend(color, .16), width=1)
        old.paste(mask.crop((60, 1170, 400, 1280)), (60, 1170))
        od = ImageDraw.Draw(old)
        od.text((80,1240), f"¥{price+20}", font=fonts[52], fill=color, anchor="ls")
        put(base + f"{brand}_KV_v02.png", raster(old, "PNG"), 22)
        if i in (2, 4):
            put(base + f"{brand}_KV_1080_副本.png", png, 31)
        # A flat final vector export: one group, no <text>, image embedded.
        # It is a deliverable, but it cannot replace the editable v01 source.
        final_svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">\n'
                     f'  <g id="export"><rect width="1080" height="1440" fill="{bg}"/>'
                     f'<image href="{brand}_KV_终版.jpg" width="1080" height="1440"/></g>\n'
                     '</svg>\n')
        put(base + f"{brand}_KV_终版.svg", final_svg.encode(), 31)
        finals.append({"project": folder, "path": base + f"{brand}_KV_终版.svg",
                       "sha256": files[-1]["sha256"], "role": "final_svg"})

    state = target / "services/files/state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"now":"2026-11-02T10:30:00+08:00", "sequence":0, "mutation_events":[]}, indent=2)+"\n", encoding="utf-8")
    (Path(__file__).parent / "truth.json").write_text(json.dumps({"fixture_version":"three-projects-v2","sources":sources,"finals":finals,"files":files}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    prompts = ROOT / "prompt/cases/种子5"
    prompts.mkdir(parents=True, exist_ok=True)
    source = (ROOT / "AAA_core_data/种子.md").read_text(encoding="utf-8").split("# 种子5\n",1)[1].split("# 种子6",1)[0]
    instructions = [line.split("|")[2].strip() for line in source.splitlines() if line.startswith("| 测试指令 |")]
    variants = {}
    for key, text in zip(("ru_test",), instructions):
        (prompts / f"{key}.md").write_text(text+"\n", encoding="utf-8")
        variants[key] = {"category":"Requirement Underspecification", "instruction_type":"test", "user_prompt":key+".md"}
    (prompts / "config.json").write_text(json.dumps({"groups":["files"],"evaluator":"seed5","variants":variants}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    build()

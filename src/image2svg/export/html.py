from __future__ import annotations

import base64
import json
from pathlib import Path

from image2svg.core.scene import Scene

_OVERVIEW_WIDTH = 1500
_PATCH_WIDTH = 260


def _data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _to_png_bytes(image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def export_html(
    scene: Scene,
    original_path: Path,
    render_path: Path,
    output_path: Path,
) -> Path:
    """Interactive review page: overview with numbered boxes + per-part patches."""
    from PIL import Image

    original = Image.open(original_path).convert("RGB")
    rendered = Image.open(render_path).convert("RGB")

    if original.width > _OVERVIEW_WIDTH:
        overview_original = original.resize(
            (_OVERVIEW_WIDTH, int(original.height * _OVERVIEW_WIDTH / original.width))
        )
    else:
        overview_original = original
    overview_scale = overview_original.width / scene.width

    if rendered.width > _OVERVIEW_WIDTH:
        overview_render = rendered.resize(
            (_OVERVIEW_WIDTH, int(rendered.height * _OVERVIEW_WIDTH / rendered.width))
        )
    else:
        overview_render = rendered

    elements = []
    for index, element in enumerate(scene.elements):
        x, y, w, h = element.bbox
        etype = element.type
        if etype == "group" and (element.style or {}).get("arrow_start"):
            etype = "arrow"
        pad = max(6.0, min(w, h) * 0.15)
        box = (
            max(0, int(x - pad)),
            max(0, int(y - pad)),
            min(scene.width, int(x + w + pad)),
            min(scene.height, int(y + h + pad)),
        )
        patch_orig = original.crop(box)
        patch_rend = rendered.crop(box)
        if patch_orig.width > 0:
            height_scale = _PATCH_WIDTH / patch_orig.width
            patch_orig = patch_orig.resize(
                (_PATCH_WIDTH, max(24, int(patch_orig.height * height_scale)))
            )
            patch_rend = patch_rend.resize(
                (_PATCH_WIDTH, max(24, int(patch_rend.height * height_scale)))
            )
        elements.append(
            {
                "i": index,
                "id": element.id,
                "type": etype,
                "text": element.text or "",
                "x": round(x, 1),
                "y": round(y, 1),
                "w": round(w, 1),
                "h": round(h, 1),
                "op": _data_uri(_to_png_bytes(patch_orig)),
                "rp": _data_uri(_to_png_bytes(patch_rend)),
            }
        )

    payload = {
        "width": scene.width,
        "height": scene.height,
        "scale": overview_scale,
        "ov_w": overview_original.width,
        "ov_h": overview_original.height,
        "orig": _data_uri(_to_png_bytes(overview_original)),
        "rend": _data_uri(_to_png_bytes(overview_render)),
        "elements": elements,
    }
    html = _TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>image2svg review</title>
<style>
body{font-family:Arial,sans-serif;margin:16px;background:#f5f6f8}
h2,h3{margin:14px 0 8px}
.pair{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.frame{position:relative;background:#fff;border:1px solid #ccc;overflow:visible}
.frame img{display:block;width:auto;height:auto;max-width:100%}
.box{position:absolute;border:1.5px solid #ff2d55;background:rgba(255,45,85,.06)}
.num{position:absolute;top:-14px;left:-2px;background:#ff2d55;color:#fff;font-size:11px;padding:1px 5px;border-radius:3px;white-space:nowrap;cursor:pointer}
.cards{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px}
.card{background:#fff;border:1px solid #ddd;padding:8px;width:300px}
.card .crop{display:flex;gap:6px}
.card img{width:140px;height:auto;display:block;border:1px solid #eee}
.card .meta{font-size:12px;margin:6px 0;color:#333;word-break:break-all}
.note{width:100%;border:1px solid #bbb;box-sizing:border-box}
button{margin-top:12px;padding:6px 14px;cursor:pointer}
</style></head><body>
<h2>image2svg 部件审查</h2>
<p>总览：每个部件有编号红框；点编号跳转到下面的细节 patch。在 patch 卡片里写问题备注，最后点“复制备注”粘给我。</p>

<h3>总览（左：原图 右：生成图）</h3>
<div class="pair">
 <div class="frame" id="f1"></div>
 <div class="frame" id="f2"></div>
</div>

<h3>细节 patch（每个部件：左原图裁剪 右生成图裁剪）</h3>
<div class="cards" id="cards"></div>
<button onclick="copyNotes()">复制备注（JSON）</button>

<script>
const DATA = __DATA__;
function buildFrame(id, src, withBoxes){
  const c=document.getElementById(id);
  const img=document.createElement('img');img.src=src;c.appendChild(img);
  if(!withBoxes) return;
  DATA.elements.forEach(el=>{
    const d=document.createElement('div');d.className='box';
    d.style.left=(el.x*DATA.scale)+'px';d.style.top=(el.y*DATA.scale)+'px';
    d.style.width=(el.w*DATA.scale)+'px';d.style.height=(el.h*DATA.scale)+'px';
    const n=document.createElement('span');n.className='num';n.textContent=el.i;
    n.onclick=()=>{const t=document.getElementById('p_'+el.i);if(t){t.scrollIntoView({behavior:'smooth'});t.style.outline='3px solid #ff2d55';setTimeout(()=>t.style.outline='',1500);}};
    d.appendChild(n);c.appendChild(d);
  });
}
buildFrame('f1', DATA.orig, true);
buildFrame('f2', DATA.rend, false);

const cards=document.getElementById('cards');
DATA.elements.forEach(el=>{
  const card=document.createElement('div');card.className='card';card.id='p_'+el.i;
  const meta=document.createElement('div');meta.className='meta';
  meta.textContent='#'+el.i+' '+el.id+' ['+el.type+'] '+el.text+'  ('+el.x+','+el.y+','+el.w+'x'+el.h+')';
  const crop=document.createElement('div');crop.className='crop';
  const o=document.createElement('img');o.src=el.op;o.title='原图';
  const r=document.createElement('img');r.src=el.rp;r.title='生成';
  crop.appendChild(o);crop.appendChild(r);
  const inp=document.createElement('input');inp.className='note';inp.placeholder='问题备注…';
  card.appendChild(meta);card.appendChild(crop);card.appendChild(inp);
  cards.appendChild(card);
});
function copyNotes(){
  const out=[];
  document.querySelectorAll('.card').forEach(card=>{
    const note=card.querySelector('.note').value.trim();
    if(note) out.push({id:card.querySelector('.meta').textContent.split(' ')[1], note});
  });
  navigator.clipboard.writeText(JSON.stringify(out,null,2)).then(()=>alert('已复制 '+out.length+' 条备注'));
}
</script></body></html>
"""

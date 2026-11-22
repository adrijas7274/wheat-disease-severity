"""Scroll-to-zoom / drag-to-pan for a Gradio image with elem_id="zoom-view".
Shared by the mask annotation tool and the rating tool."""

# Scroll-to-zoom and drag-to-pan on the click view. Implemented as a CSS
# transform on the <img>: Gradio maps a click to image pixels via the img's
# getBoundingClientRect(), which includes the transform, so clicks stay
# pixel-accurate while zoomed. A click that ends a drag is swallowed (capture
# phase) so panning never adds a SAM/wand point.
ZOOM_JS = """
() => {
  const root = document.getElementById('zoom-view');
  if (!root || root.dataset.zoomInit) return;
  root.dataset.zoomInit = '1';
  const z = {s: 1, x: 0, y: 0, drag: null, moved: false};
  const img = () => root.querySelector('img');
  const apply = () => {
    const i = img(); if (!i) return;
    i.style.transformOrigin = '0 0';
    i.style.transform = `translate(${z.x}px, ${z.y}px) scale(${z.s})`;
    i.draggable = false;
  };
  window.__annZoomReset = () => { z.s = 1; z.x = 0; z.y = 0; apply(); };
  root.addEventListener('wheel', (e) => {
    const i = img(); if (!i) return;
    e.preventDefault();
    const r = i.getBoundingClientRect();
    const ox = r.left - z.x, oy = r.top - z.y;          // untransformed img origin
    const u = (e.clientX - ox - z.x) / z.s, v = (e.clientY - oy - z.y) / z.s;
    const s2 = Math.min(20, Math.max(1, z.s * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
    z.x = e.clientX - ox - s2 * u; z.y = e.clientY - oy - s2 * v; z.s = s2;
    if (z.s === 1) { z.x = 0; z.y = 0; }
    apply();
  }, {passive: false});
  root.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    z.drag = {cx: e.clientX, cy: e.clientY, x: z.x, y: z.y}; z.moved = false;
  });
  window.addEventListener('mousemove', (e) => {
    if (!z.drag) return;
    const dx = e.clientX - z.drag.cx, dy = e.clientY - z.drag.cy;
    if (!z.moved && Math.hypot(dx, dy) < 4) return;
    z.moved = true; z.x = z.drag.x + dx; z.y = z.drag.y + dy; apply();
  });
  window.addEventListener('mouseup', () => { z.drag = null; });
  root.addEventListener('click', (e) => {
    if (z.moved) { e.stopPropagation(); e.preventDefault(); z.moved = false; }
  }, true);
  root.addEventListener('dragstart', (e) => e.preventDefault());
  new MutationObserver(apply).observe(root, {subtree: true, childList: true, attributes: true, attributeFilter: ['src']});
}
"""
ZOOM_RESET_JS = "() => { if (window.__annZoomReset) window.__annZoomReset(); }"
CSS = "#zoom-view { overflow: hidden !important; } #zoom-view img { cursor: crosshair; }"

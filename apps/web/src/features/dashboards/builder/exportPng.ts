/**
 * Export a widget's chart as a PNG with no library (spec s.6): the card's single Recharts SVG is
 * cloned, its text styles inlined, serialised, drawn on a canvas at 2x, and framed with the title,
 * a caption line (filters, dates, "Data to ...") and the legend read from the card's HTML legend
 * (HTML legends do not serialise with the SVG).
 */

export type PngFrame = {
  title: string;
  caption: string;
  background: string;
  text: string;
  muted: string;
};

/** The chart SVG of a card, or why there is none to export. */
export function exportableSvg(root: HTMLElement | null): { svg: SVGSVGElement | null; reason: string | null } {
  if (!root) return { svg: null, reason: 'Nothing to export yet.' };
  const svgs = Array.from(root.querySelectorAll<SVGSVGElement>('svg.recharts-surface'));
  if (svgs.length === 1) return { svg: svgs[0], reason: null };
  if (svgs.length === 0) return { svg: null, reason: 'Image export is for charts; use CSV.' };
  return { svg: null, reason: 'This chart has more than one drawing; use CSV.' };
}

type LegendItem = { label: string; color: string };

function legendItems(root: HTMLElement): LegendItem[] {
  const items: LegendItem[] = [];
  root.querySelectorAll<HTMLElement>('[data-testid="chart-legend"] li, [data-testid="share-chart-legend"] li').forEach((li) => {
    const swatch = li.querySelector<HTMLElement>('[aria-hidden="true"], [aria-hidden]');
    const label = (li.textContent ?? '').trim();
    if (!label) return;
    const color = swatch ? getComputedStyle(swatch).backgroundColor : '#888';
    items.push({ label, color });
  });
  return items;
}

function inlineTextStyles(source: SVGSVGElement, clone: SVGSVGElement) {
  const src = source.querySelectorAll<SVGElement>('text, tspan');
  const dst = clone.querySelectorAll<SVGElement>('text, tspan');
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const target = dst[i];
    if (!target) return;
    target.setAttribute('font-family', cs.fontFamily || 'sans-serif');
    target.setAttribute('font-size', cs.fontSize || '11px');
    const fill = el.getAttribute('fill') || cs.fill;
    if (fill) target.setAttribute('fill', fill);
  });
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (ctx.measureText(next).width > maxWidth && cur) {
      lines.push(cur);
      cur = w;
    } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines;
}

/** Axis captions are HTML, so include their units in the exported canvas frame as well. */
export function imageCaption(root: HTMLElement, caption: string): string {
  const axes = Array.from(root.querySelectorAll<HTMLElement>('[data-testid^="chart-axis-title-"]'))
    .map((el) => el.textContent?.trim()).filter((s): s is string => Boolean(s));
  return [caption, ...new Set(axes)].filter(Boolean).join(' · ');
}

/** Render the card's chart to a PNG Blob. Resolves null when the browser cannot draw it. */
export async function chartToPng(root: HTMLElement, frame: PngFrame): Promise<Blob | null> {
  const { svg } = exportableSvg(root);
  if (!svg) return null;
  const rect = svg.getBoundingClientRect();
  const width = Math.max(320, Math.round(rect.width || Number(svg.getAttribute('width')) || 640));
  const height = Math.max(160, Math.round(rect.height || Number(svg.getAttribute('height')) || 320));
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));
  inlineTextStyles(svg, clone);
  const xml = new XMLSerializer().serializeToString(clone);
  const url = URL.createObjectURL(new Blob([xml], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error('The chart image could not be drawn.'));
      i.src = url;
    });
    const scale = 2;
    const pad = 16;
    const legend = legendItems(root);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.font = '12px sans-serif';
    const captionLines = wrapLines(ctx, imageCaption(root, frame.caption), width);
    const legendRows = legend.length ? Math.ceil(legend.length / 3) : 0;
    const top = pad + 22 + captionLines.length * 16 + (legendRows ? legendRows * 18 + 6 : 0) + 8;
    canvas.width = (width + pad * 2) * scale;
    canvas.height = (top + height + pad) * scale;
    ctx.scale(scale, scale);
    ctx.fillStyle = frame.background;
    ctx.fillRect(0, 0, width + pad * 2, top + height + pad);
    ctx.fillStyle = frame.text;
    ctx.font = '600 15px sans-serif';
    ctx.fillText(frame.title, pad, pad + 14);
    ctx.font = '12px sans-serif';
    ctx.fillStyle = frame.muted;
    captionLines.forEach((l, i) => ctx.fillText(l, pad, pad + 34 + i * 16));
    let y = pad + 34 + captionLines.length * 16 + 4;
    const colW = width / 3;
    legend.forEach((it, i) => {
      const cx = pad + (i % 3) * colW;
      const cy = y + Math.floor(i / 3) * 18;
      ctx.fillStyle = it.color;
      ctx.fillRect(cx, cy - 9, 10, 10);
      ctx.fillStyle = frame.muted;
      const label = it.label.length > 40 ? `${it.label.slice(0, 39)}…` : it.label;
      ctx.fillText(label, cx + 14, cy);
    });
    y = top;
    ctx.drawImage(img, pad, y, width, height);
    return await new Promise<Blob | null>((resolve) => canvas.toBlob((b) => resolve(b), 'image/png'));
  } finally {
    URL.revokeObjectURL(url);
  }
}

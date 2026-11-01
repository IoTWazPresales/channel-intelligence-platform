'use client';

import { useEffect, useRef, useState, type RefObject } from 'react';

const MIN_PLOT = 120;
// A box whose own height follows its content would make the plot taller every measure. No widget needs more.
const MAX_PLOT = 900;

/**
 * Plot height that makes a chart fill its widget, so a chart can use the box instead of a fixed plot.
 *
 * The box is a flex child with a fixed height; the chart sits inside it beside controls, a legend or notes.
 * So the plot is the box height minus those extras (the plot's in-flow siblings, summed).
 * `undefined` until a chart has drawn, which leaves the component's own default height.
 *
 * The box element can be replaced (the card re-keys its fade when data arrives), so the observers
 * follow `ref.current` on every render instead of binding to the first element.
 */
export function useBoxHeight(ref: RefObject<HTMLElement | null>): number | undefined {
  const [height, setHeight] = useState<number | undefined>(undefined);
  const bound = useRef<{ el: HTMLElement; stop: () => void } | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (el === bound.current?.el) return;
    bound.current?.stop();
    bound.current = null;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let frame = 0;
    // Content moves without the box resizing (legend wraps, controls appear, fonts load), so the
    // plot and every leaf are observed too; observe() on an observed node is a no-op.
    const resize = new ResizeObserver(() => schedule());
    const measure = () => {
      frame = 0;
      const box = el.clientHeight;
      const plot = el.querySelector<HTMLElement>('.recharts-wrapper');
      if (box <= 48 || !plot) return;
      // Extras = in-flow siblings of the plot at every level up to the box (controls, legend, notes).
      // Each is observed, so a legend that wraps or a note that appears re-measures the plot.
      resize.observe(plot);
      let extras = 0;
      for (let node: HTMLElement = plot; node !== el && node.parentElement; node = node.parentElement) {
        for (const sib of Array.from(node.parentElement.children)) {
          if (sib === node) continue;
          resize.observe(sib);
          const cs = getComputedStyle(sib);
          if (cs.position === 'absolute' || cs.position === 'fixed' || cs.display === 'none') continue;
          extras += sib.getBoundingClientRect().height;
        }
      }
      const own = getComputedStyle(el);
      extras += (parseFloat(own.paddingTop) || 0) + (parseFloat(own.paddingBottom) || 0);
      const next = Math.min(MAX_PLOT, Math.max(MIN_PLOT, Math.floor(box - extras - 2)));
      setHeight((prev) => (prev === next ? prev : next));
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    schedule();
    resize.observe(el);
    const mutate = new MutationObserver(schedule);
    mutate.observe(el, { childList: true, subtree: true });
    bound.current = {
      el,
      stop: () => {
        resize.disconnect();
        mutate.disconnect();
        if (frame) cancelAnimationFrame(frame);
      },
    };
  });
  useEffect(() => () => bound.current?.stop(), []);
  return height;
}

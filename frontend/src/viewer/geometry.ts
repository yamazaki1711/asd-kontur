export type NormalizedRegion = readonly [number, number, number, number];

export function normalizedToCss(
  region: NormalizedRegion,
  width: number,
  height: number,
) {
  const [x0, y0, x1, y1] = region;
  if (![x0, y0, x1, y1].every((value) => value >= 0 && value <= 1)) {
    throw new Error("normalized_region_out_of_bounds");
  }
  if (x0 >= x1 || y0 >= y1 || width <= 0 || height <= 0) {
    throw new Error("normalized_region_invalid");
  }
  return {
    left: x0 * width,
    top: y0 * height,
    width: (x1 - x0) * width,
    height: (y1 - y0) * height,
  };
}

export function cssToNormalized(
  box: { left: number; top: number; width: number; height: number },
  pageWidth: number,
  pageHeight: number,
): NormalizedRegion {
  if (pageWidth <= 0 || pageHeight <= 0 || box.width <= 0 || box.height <= 0) {
    throw new Error("css_region_invalid");
  }
  return [
    box.left / pageWidth,
    box.top / pageHeight,
    (box.left + box.width) / pageWidth,
    (box.top + box.height) / pageHeight,
  ];
}

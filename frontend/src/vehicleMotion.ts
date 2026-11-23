type Point = [number, number];

export function motionAlongLane(shape: number[][], from: Point, to: Point) {
  const longitudeScale = Math.cos(shape[0][1] * Math.PI / 180);
  let distance = 0;
  let fromOffset = 0, toOffset = 0, fromError = Infinity, toError = Infinity;
  const segments: { a: number[]; dx: number; dy: number; start: number; length: number }[] = [];

  for (let index = 1; index < shape.length; index++) {
    const a = shape[index - 1], b = shape[index];
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const scaledX = dx * longitudeScale;
    const length = Math.hypot(scaledX, dy);
    if (!length) continue;

    const project = (point: Point) => {
      const x = (point[0] - a[0]) * longitudeScale, y = point[1] - a[1];
      const fraction = Math.max(0, Math.min(1, (x * scaledX + y * dy) / (length * length)));
      return { offset: distance + fraction * length, error: Math.hypot(x - fraction * scaledX, y - fraction * dy) };
    };
    const start = project(from), end = project(to);
    if (start.error < fromError) { fromError = start.error; fromOffset = start.offset; }
    if (end.error < toError) { toError = end.error; toOffset = end.offset; }
    segments.push({ a, dx, dy, start: distance, length });
    distance += length;
  }

  return (fraction: number): { coordinates: Point; angle: number } | undefined => {
    if (fraction >= 1) return;
    const offset = fromOffset + (toOffset - fromOffset) * fraction;
    const segment = segments.find(item => offset <= item.start + item.length);
    if (!segment) return;
    const along = (offset - segment.start) / segment.length;
    const bearing = Math.atan2(segment.dx * longitudeScale, segment.dy) * 180 / Math.PI;
    return {
      coordinates: [segment.a[0] + segment.dx * along, segment.a[1] + segment.dy * along],
      angle: (bearing + 360) % 360,
    };
  };
}

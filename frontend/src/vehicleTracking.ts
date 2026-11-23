import type { Vehicle } from './types';

export type TrackingSlots = [string | null, string | null];
export type TrackedVehicle = { slot: number; vehicle: Vehicle };
export const trackingColors = ['#28bde9', '#ffc25c'];

export function toggleTracking(slots: TrackingSlots, id: string): TrackingSlots {
  if (slots[0] === id) return [null, slots[1]];
  if (slots[1] === id) return [slots[0], null];
  if (slots[0] === null) return [id, slots[1]];
  if (slots[1] === null) return [slots[0], id];
  return slots;
}

export function remainingTrackingRoute(vehicle: Vehicle): string[] {
  const reportedIndex = vehicle.route_index ?? -1;
  if (vehicle.road.startsWith(':') && reportedIndex >= 0) return vehicle.route.slice(reportedIndex + 1);
  const index = vehicle.route[reportedIndex] === vehicle.road
    ? reportedIndex : vehicle.route.indexOf(vehicle.road);
  return vehicle.route.slice(Math.max(0, index));
}

export function trimTrackingLine(shape: number[][], point: [number, number]): number[][] {
  const longitudeScale = Math.cos(point[1] * Math.PI / 180);
  let start = shape[0];
  let nextIndex = 1;
  let closest = Infinity;
  for (let i = 1; i < shape.length; i++) {
    const a = shape[i - 1], b = shape[i];
    const dx = (b[0] - a[0]) * longitudeScale, dy = b[1] - a[1];
    const lengthSquared = dx * dx + dy * dy;
    if (!lengthSquared) continue;
    const x = (point[0] - a[0]) * longitudeScale, y = point[1] - a[1];
    const fraction = Math.max(0, Math.min(1, (x * dx + y * dy) / lengthSquared));
    const distance = Math.hypot(x - dx * fraction, y - dy * fraction);
    if (distance >= closest) continue;
    closest = distance;
    start = [a[0] + (b[0] - a[0]) * fraction, a[1] + dy * fraction];
    nextIndex = i;
  }
  return [start, ...shape.slice(nextIndex)];
}

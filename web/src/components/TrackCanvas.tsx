import { useEffect, useMemo, useRef } from "react";
import { carPositionsBounds, rotatePoint, trackBounds } from "../geometry";
import { carPoseAt } from "../replay";
import type { CarSeries, RaceManifest } from "../types";

const LABEL_L = "#e8eaed";

/** Rotated static geometry for one race: centreline polyline and corner labels.
 * Tolerates the degraded shape (empty points, absent corners, rotation 0) the
 * exporter produces when the track cannot be built. */
function useTrackGeometry(race: RaceManifest) {
  return useMemo(() => {
    const deg = race.track.rotation_deg;
    const points = race.track.points ?? [];
    const line = points.map(([x, y]) => rotatePoint(x, y, deg));
    const corners = (race.track.corners ?? []).map((c) => {
      const [x, y] = rotatePoint(c.x, c.y, deg);
      return { label: `${c.number}${c.letter}`, x, y };
    });
    const bounds = trackBounds(points, deg);
    return { line, corners, bounds };
  }, [race]);
}

/** The track map: canvas, not DOM nodes. The centreline comes from
 * race.json track.points rotated by track.rotation_deg exactly like
 * modules/utils.py rotate(); every car is one marker in its driver color with
 * its code, drawn at the interpolated pose for the current clock time. A car
 * whose samples are null is NOT drawn — a retired car disappears. When the
 * artifact is degraded (track.points empty, e.g. circuit metadata unavailable)
 * no road is drawn and the view is fitted to the car positions instead, so
 * the cars remain visible. */
export function TrackCanvas({
  race,
  cars,
  t,
}: {
  race: RaceManifest;
  cars: CarSeries[];
  t: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const geometry = useTrackGeometry(race);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 640;
    const height = canvas.clientHeight || 480;
    if (canvas.width !== Math.round(width * dpr)) canvas.width = Math.round(width * dpr);
    if (canvas.height !== Math.round(height * dpr)) canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const { line, corners, bounds } = geometry;
    const pad = 34;
    // Degraded path: no centreline means the track bounds are meaningless
    // (Infinity); fit the view to the cars instead so they stay visible.
    const view =
      line.length > 0
        ? bounds
        : (carPositionsBounds(cars, race.track.rotation_deg) ?? {
            minX: 0,
            maxX: 0,
            minY: 0,
            maxY: 0,
          });
    const spanX = view.maxX - view.minX || 1;
    const spanY = view.maxY - view.minY || 1;
    const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
    const offX = (width - spanX * scale) / 2;
    const offY = (height - spanY * scale) / 2;
    // Canvas y grows downwards; the artifact's y grows upwards, so flip it.
    const px = (x: number) => offX + (x - view.minX) * scale;
    const py = (y: number) => height - (offY + (y - view.minY) * scale);

    // Centreline (absent in the degraded path: no road is drawn).
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    if (line.length > 1) {
      ctx.beginPath();
      ctx.moveTo(px(line[0][0]), py(line[0][1]));
      for (let i = 1; i < line.length; i++) ctx.lineTo(px(line[i][0]), py(line[i][1]));
      ctx.strokeStyle = "#3a4250";
      ctx.lineWidth = 10;
      ctx.stroke();
      ctx.strokeStyle = "#8b95a6";
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }

    // Corner labels.
    ctx.font = "500 10px system-ui, sans-serif";
    ctx.fillStyle = "#77818f";
    for (const c of corners) ctx.fillText(c.label, px(c.x) - 3, py(c.y) - 6);

    // Cars. Sorted so every code label has a chance; simple collision skip.
    const labelled: { x: number; y: number }[] = [];
    const byCode = new Map(race.drivers.map((d) => [d.code, d]));
    ctx.font = "600 11px system-ui, sans-serif";
    for (const car of cars) {
      const pose = carPoseAt(race.t0_s, race.step_s, car, t);
      if (!pose) continue; // null sample: the car is hidden, never drawn at 0,0
      const [rx, ry] = rotatePoint(pose.x, pose.y, race.track.rotation_deg);
      const x = px(rx);
      const y = py(ry);
      const driver = byCode.get(car.code);
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = driver?.color ?? "#9aa3ad";
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = "#11151b";
      ctx.stroke();
      const crowded = labelled.some((p) => Math.abs(p.x - x) < 26 && Math.abs(p.y - y) < 12);
      if (!crowded) {
        ctx.fillStyle = LABEL_L;
        ctx.fillText(car.code, x + 8, y - 6);
        labelled.push({ x, y });
      }
    }
  }, [race, cars, t, geometry]);

  return (
    <canvas
      ref={canvasRef}
      className="track-canvas"
      role="img"
      aria-label={`Mapa del circuito con la posición de los coches`}
    />
  );
}

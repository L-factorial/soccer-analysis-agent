export const MARKER_SCALE = 1.2;
export const MOBILE_PLAYER_SCALE = 0.8;
export const PLAYER_DIAMETER = 26 * MARKER_SCALE;
export const PLAYER_RING_DIAMETER = 32 * MARKER_SCALE;
export const BALL_DIAMETER = 14 * MARKER_SCALE;

type Point = { x: number; y: number };
type PlayerCircle = Point & { radius: number };

// Positions are screen pixels. This changes only rendering, never field data.
export function getBallDisplayOffset(
  ball: Point,
  players: PlayerCircle[],
  field: { width: number; height: number },
): Point {
  if (field.width <= 0 || field.height <= 0) return { x: 0, y: 0 };
  const ballRadius = BALL_DIAMETER / 2;
  const nearest = players.reduce<PlayerCircle | undefined>((closest, player) =>
    !closest || Math.hypot(ball.x - player.x, ball.y - player.y) <
      Math.hypot(ball.x - closest.x, ball.y - closest.y) ? player : closest,
    undefined,
  );
  if (!nearest) return { x: 0, y: 0 };
  const distance = Math.hypot(ball.x - nearest.x, ball.y - nearest.y);
  const separation = nearest.radius + ballRadius + 4;
  if (distance >= separation) return { x: 0, y: 0 };

  // Prefer the ball's current side, then look around the player for room.
  const angle = distance > 0.01 ? Math.atan2(ball.y - nearest.y, ball.x - nearest.x) : 0;
  let best = ball;
  let bestScore = Infinity;
  for (let index = 0; index < 16; index += 1) {
    const candidateAngle = angle + index * Math.PI / 8;
    const candidate = {
      x: nearest.x + Math.cos(candidateAngle) * separation,
      y: nearest.y + Math.sin(candidateAngle) * separation,
    };
    const outside = Math.max(0, ballRadius - candidate.x) +
      Math.max(0, candidate.x + ballRadius - field.width) +
      Math.max(0, ballRadius - candidate.y) +
      Math.max(0, candidate.y + ballRadius - field.height);
    const overlap = players.reduce((total, player) => total + Math.max(
      0, player.radius + ballRadius + 2 - Math.hypot(candidate.x - player.x, candidate.y - player.y),
    ), 0);
    const score = outside * 1000 + overlap * 100 + Math.hypot(candidate.x - ball.x, candidate.y - ball.y);
    if (score < bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return { x: best.x - ball.x, y: best.y - ball.y };
}

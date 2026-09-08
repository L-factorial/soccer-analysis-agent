/** Check current consent before each request and before accepting its result. */
export async function runCommentaryQueue<T, R>(
  plans: T[],
  options: {
    enabled: () => boolean;
    signal: AbortSignal;
    generate: (plan: T) => Promise<R>;
    onReady: (plan: T, result: R) => void;
    onError: (plan: T) => void;
  },
): Promise<void> {
  const active = () => options.enabled() && !options.signal.aborted;
  for (const plan of plans) {
    if (!active()) return;
    try {
      const result = await options.generate(plan);
      if (!active()) return;
      options.onReady(plan, result);
    } catch {
      if (!active()) return;
      options.onError(plan);
    }
  }
}

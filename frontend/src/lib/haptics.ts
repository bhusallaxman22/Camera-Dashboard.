/** Short vibration on supporting phones (Android); a silent no-op elsewhere. */
export function haptic(pattern: number | number[] = 10): void {
  if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
    try {
      navigator.vibrate(pattern);
    } catch {
      /* blocked by the browser until a user gesture */
    }
  }
}

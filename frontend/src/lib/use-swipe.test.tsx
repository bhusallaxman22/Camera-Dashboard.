import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSwipe, type SwipeDir } from "./use-swipe";

function Pad({ onSwipe, canSwipe }: { onSwipe: (d: SwipeDir) => void; canSwipe?: (d: SwipeDir) => boolean }) {
  const swipe = useSwipe({ onSwipe, canSwipe });
  return (
    <div data-testid="pad" data-dx={swipe.dx} {...swipe.handlers}>
      pad
    </div>
  );
}

function drag(el: HTMLElement, dx: number, dy = 0, pointerType = "touch") {
  const base = { pointerId: 1, isPrimary: true, pointerType };
  fireEvent.pointerDown(el, { ...base, clientX: 200, clientY: 200, timeStamp: 0 });
  fireEvent.pointerMove(el, { ...base, clientX: 200 + dx / 2, clientY: 200 + dy / 2 });
  fireEvent.pointerMove(el, { ...base, clientX: 200 + dx, clientY: 200 + dy });
  fireEvent.pointerUp(el, { ...base, clientX: 200 + dx, clientY: 200 + dy });
}

describe("useSwipe", () => {
  it("commits a long horizontal drag in its direction", () => {
    const onSwipe = vi.fn();
    render(<Pad onSwipe={onSwipe} />);
    drag(screen.getByTestId("pad"), -150);
    expect(onSwipe).toHaveBeenCalledWith("left");
    drag(screen.getByTestId("pad"), 150);
    expect(onSwipe).toHaveBeenLastCalledWith("right");
  });

  it("ignores vertical scrolls, short drags, mouse input and blocked directions", () => {
    const onSwipe = vi.fn();
    render(<Pad onSwipe={onSwipe} canSwipe={(d) => d === "left"} />);
    const pad = screen.getByTestId("pad");
    drag(pad, 20, 160);
    drag(pad, -20);
    drag(pad, -150, 0, "mouse");
    drag(pad, 150);
    expect(onSwipe).not.toHaveBeenCalled();
  });
});

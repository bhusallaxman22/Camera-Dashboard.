import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api";
import type { BestPhotos as BestPhotosData } from "@/lib/types";
import { detail, file, summary } from "@/test/fixtures";
import { AnalysisPanel, sharpnessTone } from "./analysis-panel";
import { BestPhotos } from "./best-photos";
import { CritiquePanel } from "./critique-panel";
import { CullBar, CullingControls } from "./culling-controls";
import { FilesPanel } from "./files-panel";
import { Histogram } from "./histogram";
import { MetadataGrid } from "./metadata-grid";
import { PhotoActions } from "./photo-actions";
import { PhotoThumb } from "./photo-thumb";
import { RatingStars } from "./rating-stars";
import { ToastProvider } from "./ui/toast";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

describe("RatingStars", () => {
  it("sets and clears a rating", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<RatingStars value={0} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "4 stars" }));
    expect(onChange).toHaveBeenLastCalledWith(4);

    rerender(<RatingStars value={4} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "4 stars" }));
    expect(onChange).toHaveBeenLastCalledWith(0);
  });

  it("renders read-only with an accessible label", () => {
    render(<RatingStars value={3} />);
    expect(screen.getByLabelText("3 of 5 stars")).toBeInTheDocument();
  });
});

describe("CullingControls", () => {
  const base = { rating: 0, flag: "none" as const, favorite: false, needs_edit: false, exported: false };

  it("emits pick / reject / favorite updates", async () => {
    const onUpdate = vi.fn();
    render(<CullingControls photo={base} onUpdate={onUpdate} />);
    await userEvent.click(screen.getByRole("button", { name: /pick/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ flag: "pick" });
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ flag: "reject" });
    await userEvent.click(screen.getByRole("button", { name: /favorite/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ favorite: true });
    await userEvent.click(screen.getByRole("button", { name: /needs edit/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ needs_edit: true });
  });

  it("toggles an existing flag off", async () => {
    const onUpdate = vi.fn();
    render(<CullingControls photo={{ ...base, flag: "reject" }} onUpdate={onUpdate} />);
    expect(screen.getByRole("button", { name: /reject/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /pick/i })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ flag: "none" });
  });

  it("offers a thumb-zone bar with rating, favorite and flags", async () => {
    const onUpdate = vi.fn();
    render(<CullBar photo={{ ...base, rating: 2 }} onUpdate={onUpdate} />);
    const bar = screen.getByTestId("cull-bar");
    await userEvent.click(within(bar).getByRole("radio", { name: "5 stars" }));
    expect(onUpdate).toHaveBeenLastCalledWith({ rating: 5 });
    await userEvent.click(within(bar).getByRole("button", { name: "Favorite" }));
    expect(onUpdate).toHaveBeenLastCalledWith({ favorite: true });
    await userEvent.click(within(bar).getByRole("button", { name: /pick/i }));
    expect(onUpdate).toHaveBeenLastCalledWith({ flag: "pick" });
  });
});

describe("BestPhotos", () => {
  function renderBest(data: BestPhotosData) {
    vi.spyOn(api, "best").mockResolvedValue(data);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <BestPhotos receiving={false} shotToday />
      </QueryClientProvider>,
    );
  }

  it("shows measured factors rather than the blended score", async () => {
    renderBest({
      period: "today",
      period_start: "2026-10-05T00:00:00Z",
      candidates: 40,
      ai_scored: 30,
      items: [
        {
          photo: summary({ id: "a", base_filename: "DSC_0001" }),
          score: 86.4,
          aesthetic_score: 8.5,
          eye_sharpness: 70,
        },
        {
          photo: summary({ id: "b", base_filename: "DSC_0002" }),
          score: 61,
          aesthetic_score: null,
          eye_sharpness: null,
        },
      ],
    });
    const cards = await screen.findAllByTestId("best-card");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText("AI 8.5")).toBeInTheDocument();
    expect(within(cards[0]!).getByText("Eyes")).toBeInTheDocument();
    expect(within(cards[0]!).getByText("70")).toBeInTheDocument();
    expect(within(cards[0]!).queryByText("86")).not.toBeInTheDocument();
    expect(within(cards[1]!).getByText("No AI")).toBeInTheDocument();
    expect(within(cards[1]!).queryByText("Eyes")).not.toBeInTheDocument();
    expect(screen.getByText(/30 of 40 frames have an AI score/)).toBeInTheDocument();
    expect(api.best).toHaveBeenCalledWith("today");
  });

  it("is honest when no AI scores exist and offers a wider period when empty", async () => {
    renderBest({ period: "today", period_start: null, candidates: 0, ai_scored: 0, items: [] });
    expect(await screen.findByText(/No analysed frames in today/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show all time" }));
    expect(api.best).toHaveBeenLastCalledWith("all");
  });
});

describe("Histogram", () => {
  it("renders channels and flags clipping", () => {
    const l = Array.from({ length: 256 }, () => 10);
    l[255] = 5000;
    render(<Histogram histogram={{ r: l, g: l, b: l, l }} />);
    const el = screen.getByTestId("histogram");
    expect(el.querySelectorAll("path")).toHaveLength(4);
    expect(within(el).getByTitle(/Highlights at 255/)).toHaveClass("bg-bad");
  });

  it("handles a missing histogram", () => {
    render(<Histogram histogram={{}} />);
    expect(screen.getByText("No histogram")).toBeInTheDocument();
  });
});

describe("PhotoThumb", () => {
  it("shows RAW/JPG badges, rating and flags", () => {
    render(<PhotoThumb photo={summary({ rating: 4, picked: true, flag: "pick", favorite: true })} />);
    const link = screen.getByTestId("photo-thumb");
    expect(link).toHaveAttribute("href", "/photos/11111111-1111-1111-1111-111111111111");
    expect(within(link).getByText("RAW")).toBeInTheDocument();
    expect(within(link).getByText("JPG")).toBeInTheDocument();
    expect(within(link).getByLabelText("4 of 5 stars")).toBeInTheDocument();
    expect(within(link).getByTitle("Pick")).toBeInTheDocument();
    expect(within(link).getByLabelText("Favorite")).toBeInTheDocument();
    expect(within(link).getByText("50mm · f/1.4 · 1/500 · ISO 400")).toBeInTheDocument();
  });

  it("dims rejected photos", () => {
    render(<PhotoThumb photo={summary({ rejected: true, flag: "reject" })} />);
    expect(screen.getByTestId("photo-thumb")).toHaveClass("opacity-45");
  });
});

describe("FilesPanel", () => {
  it("shows NAS and SMB paths and a validated download link", () => {
    render(
      <ToastProvider>
        <FilesPanel
          files={[
            file(),
            file({
              id: "dup",
              is_duplicate: true,
              filename: "DSC_0042 copy.NEF",
              nas_path: "/mnt/mainpool/photos/z6iii/raw/2026/09/30/DSC_0042 copy.NEF",
              smb_path: null,
            }),
          ]}
        />
      </ToastProvider>,
    );
    expect(screen.getByText("/mnt/mainpool/photos/z6iii/raw/2026/09/30/DSC_0042.NEF")).toBeInTheDocument();
    expect(screen.getByLabelText("Copy SMB path")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /download raw/i });
    expect(links[0]).toHaveAttribute("href", "/api/v1/files/f1/download");
    expect(screen.getByText("Duplicate")).toBeInTheDocument();
  });

  it("hides download for missing originals", () => {
    render(
      <ToastProvider>
        <FilesPanel files={[file({ exists: false })]} />
      </ToastProvider>,
    );
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /download/i })).not.toBeInTheDocument();
  });
});

describe("PhotoActions", () => {
  function renderActions(over: Parameters<typeof detail>[0]) {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <PhotoActions photo={detail(over)} />
        </ToastProvider>
      </QueryClientProvider>,
    );
  }

  it("offers JPEG and RAW downloads and hides Immich when disabled", () => {
    renderActions({});
    expect(screen.getByRole("link", { name: /jpeg/i })).toHaveAttribute("download", "DSC_0042.JPG");
    expect(screen.getByRole("link", { name: /raw/i })).toHaveAttribute("download", "DSC_0042.NEF");
    expect(screen.queryByText(/immich/i)).not.toBeInTheDocument();
  });

  it("offers an Immich lookup when enabled", () => {
    renderActions({ immich_enabled: true });
    expect(screen.getByRole("button", { name: /find in immich/i })).toBeInTheDocument();
  });

  it("links to the matched Immich asset", () => {
    renderActions({ immich_enabled: true, immich_url: "https://immich.local/photos/abc" });
    expect(screen.getByRole("link", { name: /open in immich/i })).toHaveAttribute(
      "href",
      "https://immich.local/photos/abc",
    );
    expect(screen.queryByRole("button", { name: /find in immich/i })).not.toBeInTheDocument();
  });
});

describe("AnalysisPanel", () => {
  it("renders estimates with hedged wording", () => {
    render(
      <AnalysisPanel
        analysis={{
          sharpness_score: 71.2,
          sharpness_label: "Good",
          sharpness_global: 120,
          sharpness_peak: 900,
          blur_score: 0.2,
          is_blurry: false,
          brightness: 0.45,
          contrast: 0.22,
          saturation: 0.3,
          dynamic_range_ev: 9.4,
          highlight_clipping_percent: 0.1,
          shadow_clipping_percent: 0.4,
          exposure_label: "good",
          exposure_assessment: "Exposure looks balanced.",
          histogram: { l: Array(256).fill(1) },
          dominant_colors: [{ hex: "#c81e1e", fraction: 0.75 }],
          face_count: 1,
          eye_count: 2,
          faces: [
            {
              x: 0.4,
              y: 0.3,
              w: 0.2,
              h: 0.3,
              confidence: 0.9,
              sharpness: 66,
              eyes: [{ x: 0.45, y: 0.4, sharpness: 70 }],
            },
          ],
          subject_detected: true,
          warnings: ["Possible camera shake."],
          source: "preview",
          algorithm_version: "1.0",
          duration_ms: 120,
          analyzed_at: "2026-09-30T15:05:00Z",
        }}
      />,
    );
    // The headline sharpness lives in the verdict strip; the panel must not repeat it.
    expect(screen.queryByText("Estimated sharpness")).not.toBeInTheDocument();
    expect(screen.getByText("Exposure looks balanced.")).toBeInTheDocument();
    expect(screen.getByText("Possible camera shake.")).toBeInTheDocument();
    expect(screen.getByText("1 face(s) detected")).toBeInTheDocument();
    expect(screen.getByTitle("#c81e1e · 75%")).toBeInTheDocument();
  });

  it("maps sharpness to tones", () => {
    expect(sharpnessTone(80)).toBe("ok");
    expect(sharpnessTone(40)).toBe("warn");
    expect(sharpnessTone(10)).toBe("bad");
    expect(sharpnessTone(null)).toBe("neutral");
  });
});

describe("CritiquePanel and MetadataGrid", () => {
  it("renders a structured critique", () => {
    render(
      <CritiquePanel
        history={3}
        critique={{
          id: "c1",
          provider: "local",
          model_name: "heuristic",
          status: "succeeded",
          scene: "portrait",
          subject: "person",
          description: "A close portrait.",
          composition: ["Subject is centered."],
          technical: ["Eyes look sharp."],
          issues: [],
          suggestions: ["Try +1/3 EV."],
          tags: ["portrait"],
          aesthetic_score: null,
          confidence: 0.35,
          error: null,
          duration_ms: 3,
          created_at: "2026-09-30T15:05:00Z",
        }}
      />,
    );
    expect(screen.getByText("Portrait")).toBeInTheDocument();
    expect(screen.getByText("Try +1/3 EV.")).toBeInTheDocument();
    expect(screen.getByText(/3 critiques on record/)).toBeInTheDocument();
  });

  it("shows Nikon metadata", () => {
    render(<MetadataGrid photo={detail()} />);
    expect(screen.getByText("Nikon Z6III")).toBeInTheDocument();
    expect(screen.getByText("2567")).toBeInTheDocument();
    expect(screen.getByText("Vibration Reduction")).toBeInTheDocument();
  });
});

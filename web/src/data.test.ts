import { describe, expect, it } from "vitest";
import { raceArtifactDir } from "./data";

describe("raceArtifactDir — index slug to on-disk directory", () => {
  it("derives {year}/{round}-{event} from the {year}-{round}-{event} slug", () => {
    expect(
      raceArtifactDir({ year: 2026, slug: "2026-15-azerbaijan-grand-prix" }),
    ).toBe("2026/15-azerbaijan-grand-prix");
    expect(
      raceArtifactDir({ year: 2026, slug: "2026-1-australian-grand-prix" }),
    ).toBe("2026/1-australian-grand-prix");
  });

  it("rejects a slug that does not start with its own year", () => {
    expect(() => raceArtifactDir({ year: 2025, slug: "2026-1-x" })).toThrow();
  });
});

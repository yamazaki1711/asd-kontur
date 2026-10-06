import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("./viewer/PdfEvidenceViewer", () => ({
  PdfEvidenceViewer: () => null,
}));

import { ProjectEngineeringResult } from "./App";

const baseModel = {
  project: {},
  summary: {},
  facility_cards: [
    {
      facility: { facility_id: "site-A", name: "Area A" },
      pits: [],
      structures: [{ name: "Utility crossing", relationship: "within area" }],
      works: [],
    },
  ],
};

describe("project engineering structure view", () => {
  it("does not prescribe excavation pits for a project without them", () => {
    render(
      <MemoryRouter>
        <ProjectEngineeringResult
          model={baseModel}
          section="structure"
          workspaceId="00000000-0000-4000-8000-000000000001"
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Инженерные карточки объекта")).toBeInTheDocument();
    expect(screen.getByText("Utility crossing")).toBeInTheDocument();
    expect(screen.queryByText(/Котлован/)).not.toBeInTheDocument();
  });

  it("retains a documented pit when the project actually has one", () => {
    render(
      <MemoryRouter>
        <ProjectEngineeringResult
          model={{
            ...baseModel,
            facility_cards: [
              {
                ...baseModel.facility_cards[0],
                pits: [{ pit_id: "pit-A", name: "Pit A" }],
              },
            ],
          }}
          section="structure"
          workspaceId="00000000-0000-4000-8000-000000000002"
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("Котлованы: 1")).toBeInTheDocument();
    expect(screen.getByText("Pit A")).toBeInTheDocument();
  });
});

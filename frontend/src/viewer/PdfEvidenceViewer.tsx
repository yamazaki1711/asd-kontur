import { useQuery } from "@tanstack/react-query";
import {
  GlobalWorkerOptions,
  getDocument,
  PDFDocumentProxy,
  PDFPageProxy,
  TextLayer,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";

import { api, requireData } from "../api/client";
import { normalizedToCss } from "./geometry";

GlobalWorkerOptions.workerSrc = workerUrl;

export function PdfEvidenceViewer({
  workspaceId,
  documentId,
  page,
  onPage,
}: {
  workspaceId: string;
  documentId: string;
  page: number;
  onPage: (page: number) => void;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1.15);
  const [rotation, setRotation] = useState(0);
  const viewerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const task = getDocument({
      url: `/api/v1/workspaces/${workspaceId}/documents/${documentId}/content`,
      withCredentials: true,
    });
    void task.promise
      .then(setPdf)
      .catch((error: unknown) =>
        setLoadError(
          error instanceof Error ? error.message : "pdf_load_failed",
        ),
      );
    return () => {
      void task.destroy();
    };
  }, [documentId, workspaceId]);
  const evidence = useQuery({
    queryKey: ["evidence", workspaceId, documentId, page],
    enabled: pdf !== null,
    queryFn: async () => {
      const { data, error } = await api.GET(
        "/api/v1/workspaces/{workspace_id}/evidence/{document_id}/pages/{page_number}",
        {
          params: {
            path: {
              workspace_id: workspaceId,
              document_id: documentId,
              page_number: page,
            },
          },
        },
      );
      return requireData(data, error);
    },
  });
  if (loadError) return <div className="notice error">{loadError}</div>;
  if (!pdf) return <div className="center-state">Загрузка документа…</div>;
  const boundedPage = Math.min(Math.max(page, 1), pdf.numPages);
  const fit = (mode: "width" | "page") => {
    void pdf.getPage(boundedPage).then((pdfPage) => {
      const viewport = pdfPage.getViewport({
        scale: 1,
        rotation: pdfPage.rotate + rotation,
      });
      const availableWidth = Math.max(
        320,
        (viewerRef.current?.clientWidth ?? window.innerWidth) - 32,
      );
      const widthScale = availableWidth / viewport.width;
      const pageScale = Math.min(
        widthScale,
        Math.max(320, window.innerHeight - 260) / viewport.height,
      );
      setZoom(
        Math.min(3, Math.max(0.5, mode === "width" ? widthScale : pageScale)),
      );
    });
  };
  return (
    <div className="viewer-grid">
      <section className="viewer" ref={viewerRef}>
        <div className="viewer-toolbar">
          <button
            onClick={() => onPage(Math.max(1, boundedPage - 1))}
            disabled={boundedPage === 1}
          >
            ←
          </button>
          <label>
            Страница
            <input
              type="number"
              min={1}
              max={pdf.numPages}
              value={boundedPage}
              onChange={(event) => onPage(Number(event.target.value))}
            />
          </label>
          <span>/ {pdf.numPages}</span>
          <button
            onClick={() => onPage(Math.min(pdf.numPages, boundedPage + 1))}
            disabled={boundedPage === pdf.numPages}
          >
            →
          </button>
          <button
            onClick={() => setZoom((value) => Math.max(0.5, value - 0.15))}
          >
            −
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button onClick={() => setZoom((value) => Math.min(3, value + 0.15))}>
            +
          </button>
          <button onClick={() => setRotation((value) => (value + 90) % 360)}>
            ↻
          </button>
          <button onClick={() => fit("width")}>По ширине</button>
          <button onClick={() => fit("page")}>Страница целиком</button>
        </div>
        <PdfPage
          pdf={pdf}
          pageNumber={boundedPage}
          zoom={zoom}
          rotation={rotation}
          {...(evidence.data?.locator.region
            ? { region: evidence.data.locator.region }
            : {})}
        />
      </section>
      <aside className="evidence-panel">
        <h2>Источник сведений</h2>
        {evidence.isPending && <p>Получение точного фрагмента…</p>}
        {evidence.isError && (
          <p className="danger-text">Связь с исходным фрагментом не найдена.</p>
        )}
        {evidence.data && (
          <>
            <dl>
              <dt>Страница и область</dt>
              <dd>
                {evidence.data.locator.page_number} /{" "}
                {evidence.data.locator.region.join(", ")}
              </dd>
              <dt>Способ получения</dt>
              <dd>
                {extractionLabel(evidence.data.locator.extraction_method)}
              </dd>
              <dt>Состояние сведения</dt>
              <dd>{factStatusLabel(evidence.data.candidate_fact_status)}</dd>
              <dt>Требует уточнения</dt>
              <dd>{evidence.data.uncertainty.length ? "Да" : "Нет"}</dd>
            </dl>
          </>
        )}
      </aside>
    </div>
  );
}

function PdfPage({
  pdf,
  pageNumber,
  zoom,
  rotation,
  region,
}: {
  pdf: PDFDocumentProxy;
  pageNumber: number;
  zoom: number;
  rotation: number;
  region?: number[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState<PDFPageProxy | null>(null);
  const [size, setSize] = useState({ width: 1, height: 1 });
  useEffect(() => {
    void pdf.getPage(pageNumber).then(setPage);
  }, [pageNumber, pdf]);
  useEffect(() => {
    if (!page || !canvasRef.current || !textRef.current) return;
    const viewport = page.getViewport({
      scale: zoom,
      rotation: page.rotate + rotation,
    });
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    if (!context) return;
    const outputScale = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = `${String(viewport.width)}px`;
    canvas.style.height = `${String(viewport.height)}px`;
    setSize({ width: viewport.width, height: viewport.height });
    const render = page.render({
      canvas,
      canvasContext: context,
      viewport,
      transform:
        outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
    });
    const textContainer = textRef.current;
    textContainer.replaceChildren();
    let textLayer: TextLayer | null = null;
    void page.getTextContent().then((content) => {
      textLayer = new TextLayer({
        textContentSource: content,
        container: textContainer,
        viewport,
      });
      return textLayer.render();
    });
    return () => {
      render.cancel();
      textLayer?.cancel();
    };
  }, [page, rotation, zoom]);
  const overlay =
    region?.length === 4
      ? normalizedToCss(
          region as [number, number, number, number],
          size.width,
          size.height,
        )
      : null;
  return (
    <div
      className="pdf-page"
      style={{ width: size.width, height: size.height }}
    >
      <canvas
        ref={canvasRef}
        aria-label={`Страница PDF ${String(pageNumber)}`}
      />
      <div
        ref={textRef}
        className="text-layer"
        aria-label="Текстовый слой страницы"
      />
      {overlay && (
        <div
          className="locator-overlay"
          style={overlay}
          aria-label="Область исходного фрагмента"
        />
      )}
    </div>
  );
}

function extractionLabel(value: string) {
  const labels: Record<string, string> = {
    native: "Из текста исходного документа",
    native_text: "Из текста исходного документа",
    spreadsheet_cell: "Из ячейки таблицы",
    docx_paragraph: "Из абзаца документа",
    ocr: "Восстановлено со страницы документа",
    vlm: "Получено при анализе фрагмента; требуется проверка",
  };
  return labels[value] ?? "Из исходного документа";
}

function factStatusLabel(value: string) {
  if (["confirmed", "verified"].includes(value)) return "Подтверждено";
  if (value.includes("candidate")) return "Требует подтверждения";
  if (value.includes("conflict")) return "Обнаружено расхождение";
  if (value.includes("insufficient")) return "Недостаточно данных";
  return "Требует уточнения";
}

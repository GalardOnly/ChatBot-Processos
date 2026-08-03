from __future__ import annotations

import argparse
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path

from preparador_audiencia.ocr import RapidOcrEngine
from preparador_audiencia.ocr_benchmark import (
    OcrBenchmarkEngineSpec,
    load_ocr_benchmark_suite,
    run_ocr_benchmark,
    write_ocr_benchmark_report,
)

EasyOcrBox = Sequence[Sequence[float]]
EasyOcrResult = tuple[EasyOcrBox, str, float]


class RapidOcrBenchmarkAdapter:
    def __init__(self, zoom: float) -> None:
        self.zoom = zoom
        self.engine = RapidOcrEngine()

    def extract_page_text(self, page) -> str:
        return self.engine.extract_page_text(page, zoom=self.zoom)


class EasyOcrBenchmarkAdapter:
    def __init__(
        self,
        *,
        gpu: bool,
        allow_model_download: bool,
        model_dir: str | None,
    ) -> None:
        try:
            import easyocr
            import numpy as np
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError(
                "EasyOCR nao esta instalado no ambiente do benchmark."
            ) from exc

        self._np = np
        self._image_type = Image
        self._reader = easyocr.Reader(
            ["pt", "en"],
            gpu=gpu,
            model_storage_directory=model_dir,
            download_enabled=allow_model_download,
            verbose=False,
        )

    def extract_page_text(self, page) -> str:
        image_bytes = RapidOcrEngine.render_page_image(page, zoom=3.0)
        image = self._image_type.open(BytesIO(image_bytes)).convert("RGB")
        results = self._reader.readtext(
            self._np.asarray(image),
            detail=1,
            paragraph=False,
        )
        return _easyocr_text_without_marginal_artifacts(results, image.width)


def _easyocr_text_without_marginal_artifacts(
    results: Sequence[EasyOcrResult],
    image_width: int,
) -> str:
    readable: list[str] = []
    left_limit = image_width * 0.05
    right_limit = image_width * 0.95
    for box, text, _confidence in results:
        center_x = sum(float(point[0]) for point in box) / len(box)
        if center_x <= left_limit or center_x >= right_limit:
            continue
        if text.strip():
            readable.append(text)
    return "\n".join(readable)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compara motores de OCR em paginas de depoimentos policiais."
    )
    parser.add_argument("--pdf", required=True, help="PDF usado no benchmark.")
    parser.add_argument(
        "--gold",
        default="data/ocr_benchmark_police_testimony.json",
        help="Gabarito curto com paginas e frases esperadas.",
    )
    parser.add_argument(
        "--engines",
        nargs="+",
        default=["rapidocr:1.5", "rapidocr:3.0", "easyocr"],
        help="Motores: rapidocr:ZOOM e easyocr.",
    )
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "gpu"),
        default="auto",
        help="Dispositivo usado pelo EasyOCR.",
    )
    parser.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Permite que o EasyOCR baixe pesos ausentes.",
    )
    parser.add_argument(
        "--model-dir",
        help="Diretorio local dos pesos do EasyOCR.",
    )
    parser.add_argument(
        "--output",
        default="reports/benchmark-ocr-depoimentos.json",
    )
    args = parser.parse_args()

    try:
        engine_specs = [
            _engine_spec(
                value,
                device=args.device,
                allow_model_download=args.allow_model_download,
                model_dir=args.model_dir,
            )
            for value in args.engines
        ]
    except ValueError as exc:
        parser.error(str(exc))

    suite = load_ocr_benchmark_suite(args.gold)
    report = run_ocr_benchmark(args.pdf, suite, engine_specs)
    write_ocr_benchmark_report(report, args.output)

    print(f"Suite: {report.suite_id}")
    for result in report.engines:
        print(
            f"{result.name}: {result.status}, recall {result.phrase_recall:.1%}, "
            f"paginas coladas {result.glued_page_count}, {result.elapsed_ms} ms"
        )
        if result.error:
            print(f"  Motivo: {result.error}")
    print(f"Comparacao entre familias pronta: {report.comparison_ready}")
    print(f"Gate aprovado: {report.gate_passed}")
    print(f"Relatorio JSON: {args.output}")
    print(f"Relatorio Markdown: {Path(args.output).with_suffix('.md')}")


def _engine_spec(
    value: str,
    *,
    device: str,
    allow_model_download: bool,
    model_dir: str | None,
) -> OcrBenchmarkEngineSpec:
    normalized = value.strip().casefold()
    if normalized.startswith("rapidocr:"):
        try:
            zoom = float(normalized.split(":", maxsplit=1)[1])
        except ValueError as exc:
            raise ValueError(f"Zoom invalido em {value}.") from exc
        if zoom <= 0:
            raise ValueError("O zoom do RapidOCR deve ser positivo.")
        return OcrBenchmarkEngineSpec(
            name=f"rapidocr-zoom-{zoom:g}",
            family="rapidocr",
            factory=lambda zoom=zoom: RapidOcrBenchmarkAdapter(zoom),
        )
    if normalized == "easyocr":
        return OcrBenchmarkEngineSpec(
            name=f"easyocr-{device}",
            family="easyocr",
            factory=lambda: EasyOcrBenchmarkAdapter(
                gpu=_use_gpu(device),
                allow_model_download=allow_model_download,
                model_dir=model_dir,
            ),
        )
    raise ValueError(f"Motor OCR desconhecido: {value}.")


def _use_gpu(device: str) -> bool:
    if device == "cpu":
        return False
    if device == "gpu":
        return True
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


if __name__ == "__main__":
    main()

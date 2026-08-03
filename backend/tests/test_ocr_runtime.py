from preparador_audiencia.ocr import ManagedOcrEngine, OcrResult


class FakeBatchEngine:
    name = "easyocr"
    engine_version = "1.7.2"
    device = "gpu"

    def __init__(self, texts: list[str] | None = None, error: Exception | None = None):
        self.texts = texts or []
        self.error = error
        self.calls = 0

    def extract_images(self, images: list[bytes]) -> list[OcrResult]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        texts = self.texts or ["texto reconhecido"] * len(images)
        return [
            OcrResult(
                text=text,
                engine=self.name,
                engine_version=self.engine_version,
                device=self.device,
            )
            for text in texts
        ]


def _managed(tmp_path, primary, fallback=None) -> ManagedOcrEngine:
    return ManagedOcrEngine(
        provider="easyocr",
        device="gpu",
        allow_model_download=False,
        model_dir=None,
        module_dir=None,
        cache_dir=tmp_path / "ocr-cache",
        batch_size=2,
        primary_factory=lambda: primary,
        fallback_factory=(lambda: fallback) if fallback is not None else None,
    )


def test_managed_ocr_reuses_page_cache(tmp_path) -> None:
    primary = FakeBatchEngine(["primeira pagina", "segunda pagina"])
    managed = _managed(tmp_path, primary)

    first = managed.extract_images([b"imagem-1", b"imagem-2"], zoom=3.0)
    second = managed.extract_images([b"imagem-1", b"imagem-2"], zoom=3.0)

    assert primary.calls == 1
    assert [result.text for result in first] == ["primeira pagina", "segunda pagina"]
    assert all(result.cache_hit is False for result in first)
    assert all(result.cache_hit is True for result in second)


def test_managed_ocr_falls_back_when_easyocr_fails(tmp_path) -> None:
    primary = FakeBatchEngine(error=RuntimeError("modelo indisponivel"))
    fallback = FakeBatchEngine(["texto do fallback"])
    fallback.name = "rapidocr"
    fallback.engine_version = "1.4.4"
    fallback.device = "cpu"
    managed = _managed(tmp_path, primary, fallback)

    result = managed.extract_images([b"imagem"], zoom=3.0)[0]

    assert result.text == "texto do fallback"
    assert result.engine == "rapidocr"
    assert result.fallback_used is True
    assert result.warning == "easyocr_indisponivel:RuntimeError"


def test_managed_ocr_falls_back_when_primary_returns_empty_text(tmp_path) -> None:
    primary = FakeBatchEngine([""])
    fallback = FakeBatchEngine(["texto recuperado"])
    fallback.name = "rapidocr"
    managed = _managed(tmp_path, primary, fallback)

    result = managed.extract_images([b"imagem-vazia"], zoom=3.0)[0]

    assert result.text == "texto recuperado"
    assert result.fallback_used is True
    assert result.warning == "easyocr_sem_texto"

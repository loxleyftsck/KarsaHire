"""Lazy, serialized PaddleOCR adapter for local image-page inference."""

from __future__ import annotations

import os
import tempfile
import threading

_PIPELINE = None
_PIPELINE_LOCK = threading.Lock()


def recognize_png(image: bytes) -> str:
    """Run the default PaddleOCR pipeline on one normalized PNG image."""
    global _PIPELINE
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "PaddleOCR lokal belum terpasang. Ikuti bagian OCR lokal PaddleOCR di README.md."
        ) from exc

    with _PIPELINE_LOCK:
        if _PIPELINE is None:
            try:
                _PIPELINE = PaddleOCR(
                    lang=os.environ.get("RECRUITMENT_COPILOT_PADDLE_LANG", "en"),
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    device=os.environ.get("RECRUITMENT_COPILOT_PADDLE_DEVICE", "cpu"),
                )
            except Exception as exc:
                raise RuntimeError(f"PaddleOCR gagal diinisialisasi: {exc}") from exc

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_file.write(image)
                temp_path = temp_file.name
            results = _PIPELINE.predict(temp_path)
        except Exception as exc:
            raise RuntimeError(f"PaddleOCR gagal memproses halaman gambar: {exc}") from exc
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    lines = []
    for result in results:
        payload = getattr(result, "json", {})
        if callable(payload):
            payload = payload()
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            continue
        page_result = payload.get("res", payload)
        if not isinstance(page_result, dict):
            continue
        texts = page_result.get("rec_texts", [])
        lines.extend(str(text).strip() for text in texts if str(text).strip())

    if not lines:
        raise RuntimeError("PaddleOCR tidak menemukan teks yang bisa diproses.")
    return "\n".join(lines)

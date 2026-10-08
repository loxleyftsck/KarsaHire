"""Memory- and time-limited child process for untrusted PDF parsing."""

from __future__ import annotations

import base64
import io
import json
import os
import sys


PDF_WORKER_MEMORY_BYTES = 256 * 1024 * 1024
PDF_WORKER_RESULT_BYTES = 48 * 1024 * 1024


def _set_posix_memory_limit() -> None:
    if os.name == "nt":
        return
    import resource

    resource.setrlimit(
        resource.RLIMIT_AS,
        (PDF_WORKER_MEMORY_BYTES, PDF_WORKER_MEMORY_BYTES),
    )


_set_posix_memory_limit()

# Import project parsers only after applying the process limit.
import server  # noqa: E402


class PdfTextBudgetExceeded(ValueError):
    """Raised when PDF text operations exceed the application work budget."""


def _measure_text_operands(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray)):
        return len(value)
    if isinstance(value, (list, tuple)):
        return sum(_measure_text_operands(item) for item in value)
    return 0


def _extract_pdf_data(
    payload: bytes,
    *,
    max_pages: int,
    max_text_characters: int,
    max_ocr_images: int,
    max_upload_bytes: int,
    max_decoded_stream_bytes: int,
    max_ocr_image_bytes: int,
) -> tuple[list[tuple[int, str]], list[tuple[int, bytes]]]:
    try:
        from pypdf import PdfReader, apply_configuration
    except ImportError as exc:
        raise ValueError("PDF reader tidak tersedia di runtime ini.") from exc

    pages: list[tuple[int, str]] = []
    images: list[tuple[int, bytes]] = []
    total_text_characters = 0
    total_image_bytes = 0
    image_count = 0

    try:
        with apply_configuration(
            maximum_declared_stream_length=max_upload_bytes,
            array_based_stream_maximum_output_length=max_decoded_stream_bytes,
            jbig2_maximum_output_length=max_decoded_stream_bytes,
            lzw_maximum_output_length=max_decoded_stream_bytes,
            run_length_maximum_output_length=max_decoded_stream_bytes,
            zlib_maximum_output_length=max_decoded_stream_bytes,
            image_maximum_buffer_size=max_upload_bytes,
            page_tree_maximum_entries=max(1000, max_pages),
            page_tree_maximum_depth=64,
            xform_maximum_invocations_per_extraction=128,
        ):
            reader = PdfReader(io.BytesIO(payload))
            if reader.is_encrypted:
                raise ValueError("PDF terenkripsi atau terkunci belum dapat diproses.")
            page_count = len(reader.pages)
            if page_count > max_pages:
                raise ValueError(f"PDF melebihi batas {max_pages} halaman.")

            for page_number, page in enumerate(reader.pages, start=1):
                budget = {"operand_characters": 0, "exceeded": False}

                def check_text_operand(operator, operands, *_):
                    if operator in (b"Tj", b"TJ", b"'", b'"'):
                        budget["operand_characters"] += _measure_text_operands(operands)
                        if budget["operand_characters"] > max_text_characters:
                            budget["exceeded"] = True
                            raise PdfTextBudgetExceeded(
                                "Dokumen melampaui batas teks hasil ekstraksi."
                            )

                try:
                    text = page.extract_text(visitor_operand_before=check_text_operand) or ""
                except PdfTextBudgetExceeded:
                    raise
                except Exception as exc:
                    if budget["exceeded"]:
                        raise PdfTextBudgetExceeded(
                            "Dokumen melampaui batas teks hasil ekstraksi."
                        ) from exc
                    raise ValueError(
                        f"Halaman {page_number} PDF rusak atau tidak dapat dibaca."
                    ) from exc
                if budget["exceeded"]:
                    raise PdfTextBudgetExceeded(
                        "Dokumen melampaui batas teks hasil ekstraksi."
                    )

                total_text_characters += len(text)
                if total_text_characters > max_text_characters:
                    raise PdfTextBudgetExceeded(
                        "Dokumen melampaui batas teks hasil ekstraksi."
                    )
                if text.strip():
                    pages.append((page_number, text))
                    continue

                try:
                    with apply_configuration(
                        maximum_declared_stream_length=max_upload_bytes,
                        array_based_stream_maximum_output_length=max_upload_bytes,
                        jbig2_maximum_output_length=max_upload_bytes,
                        lzw_maximum_output_length=max_upload_bytes,
                        run_length_maximum_output_length=max_upload_bytes,
                        zlib_maximum_output_length=max_upload_bytes,
                        image_maximum_buffer_size=max_upload_bytes,
                        page_tree_maximum_entries=max(1000, max_pages),
                        page_tree_maximum_depth=64,
                        xform_maximum_invocations_per_extraction=128,
                    ):
                        embedded_images = list(getattr(page, "images", []))
                        for embedded in embedded_images:
                            image_count += 1
                            if image_count > max_ocr_images:
                                raise ValueError(
                                    f"PDF melebihi batas {max_ocr_images} gambar tertanam untuk OCR."
                                )
                            try:
                                image_data = embedded.data
                                normalized_image = server.normalize_image(image_data)
                            except ValueError:
                                continue
                            except Exception as exc:
                                raise ValueError(
                                    f"Gambar halaman {page_number} PDF rusak atau tidak dapat dibaca."
                                ) from exc
                            total_image_bytes += len(normalized_image)
                            if total_image_bytes > max_ocr_image_bytes:
                                raise ValueError("PDF melebihi batas ukuran total gambar untuk OCR.")
                            images.append((page_number, normalized_image))
                except Exception as exc:
                    if isinstance(exc, ValueError) and str(exc).startswith("PDF melebihi batas"):
                        raise
                    raise ValueError(
                        f"Gambar halaman {page_number} PDF rusak atau tidak dapat dibaca."
                    ) from exc

                if not embedded_images:
                    raise ValueError(
                        f"Halaman {page_number} tidak memiliki teks atau gambar yang bisa dikirim ke OCR."
                    )
    except (PdfTextBudgetExceeded, ValueError):
        raise
    except Exception as exc:
        raise ValueError("PDF rusak atau tidak dapat dibaca.") from exc

    return pages, images


def _main() -> int:
    try:
        (
            max_pages,
            max_text_characters,
            max_ocr_images,
            max_upload_bytes,
            max_decoded_stream_bytes,
            max_ocr_image_bytes,
        ) = (int(argument) for argument in sys.argv[1:7])
    except (TypeError, ValueError):
        return 2

    payload = sys.stdin.buffer.read(max_upload_bytes + 1)
    if len(payload) > max_upload_bytes:
        response = {"ok": False, "error": "File melampaui batas unggahan 8 MB."}
    else:
        try:
            pages, images = _extract_pdf_data(
                payload,
                max_pages=max_pages,
                max_text_characters=max_text_characters,
                max_ocr_images=max_ocr_images,
                max_upload_bytes=max_upload_bytes,
                max_decoded_stream_bytes=max_decoded_stream_bytes,
                max_ocr_image_bytes=max_ocr_image_bytes,
            )
            response = {
                "ok": True,
                "pages": [[page_number, text] for page_number, text in pages],
                "images": [
                    [page_number, base64.b64encode(image).decode("ascii")]
                    for page_number, image in images
                ],
            }
        except ValueError as exc:
            response = {"ok": False, "error": str(exc)[:256]}
        except Exception:
            response = {"ok": False, "error": "PDF rusak atau tidak dapat dibaca."}

    output = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(output) > PDF_WORKER_RESULT_BYTES:
        output = json.dumps(
            {"ok": False, "error": "PDF melampaui batas keluaran parser."},
            separators=(",", ":"),
        ).encode("utf-8")
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

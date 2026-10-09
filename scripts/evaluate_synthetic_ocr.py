"""Measure OCR text error on one explicitly selected synthetic PDF.

The default invocation is a no-network preflight. OCR can run through the
configured internal endpoint (explicit opt-in), local Tesseract, or Windows OCR.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "synthetic-cv-32"
WINDOWS_OCR_BRIDGE = Path(__file__).with_name("windows_ocr_bridge.ps1")
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def resolve_dataset_file(path: Path) -> Path:
    """Resolve a corpus file while rejecting links outside this repository."""
    try:
        repository_root = ROOT.resolve(strict=True)
        dataset_root = DATASET.resolve(strict=True)
        dataset_root.relative_to(repository_root)
        resolved = path.resolve(strict=True)
        resolved.relative_to(dataset_root)
    except (OSError, ValueError) as error:
        raise ValueError("Path file evaluasi harus berada di korpus sintetis dalam repository.") from error
    if not resolved.is_file():
        raise ValueError("File evaluasi korpus sintetis tidak tersedia.")
    return resolved


def tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return re.findall(r"[^\W_]+(?:[+#.][^\W_]+|[+#]+)*", normalized, flags=re.UNICODE)


def word_error_counts(reference: list[str], hypothesis: list[str]) -> tuple[int, int]:
    """Return Levenshtein word edits and reference-token count (WER denominator)."""
    previous = list(range(len(hypothesis) + 1))
    for ref_index, ref_word in enumerate(reference, start=1):
        current = [ref_index]
        for hyp_index, hyp_word in enumerate(hypothesis, start=1):
            current.append(min(
                current[-1] + 1,
                previous[hyp_index] + 1,
                previous[hyp_index - 1] + (ref_word != hyp_word),
            ))
        previous = current
    return previous[-1], len(reference)


def preflight(sample_id: str) -> tuple[Path, Path, int, int]:
    manifest_path = resolve_dataset_file(DATASET / "manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    known_ids = {
        str(entry.get("sample_id", ""))
        for entry in manifest
        if isinstance(entry, dict)
    }
    if sample_id not in known_ids or not re.fullmatch(r"r\d{5}", sample_id):
        raise ValueError("Pilih sample_id yang tercantum di korpus sintetis lokal.")

    pdf_path = resolve_dataset_file(DATASET / sample_id / f"{sample_id}.pdf")
    reference_path = resolve_dataset_file(DATASET / sample_id / "resume_text.txt")

    reader = PdfReader(str(pdf_path), strict=True)
    ocr_image_count = 0
    for page_num, page in enumerate(reader.pages, start=1):
        if (page.extract_text() or "").strip():
            continue
        images = getattr(page, "images", [])
        if not images:
            raise ValueError(f"Halaman {page_num} tidak memiliki teks atau gambar OCR.")
        ocr_image_count += len(images)

    if ocr_image_count == 0:
        raise ValueError("PDF terpilih tidak memiliki halaman scan untuk diuji OCR.")
    if ocr_image_count > server.MAX_OCR_IMAGES_PER_PDF:
        raise ValueError(
            f"Sampel membutuhkan {ocr_image_count} gambar OCR; batas satu run "
            f"adalah {server.MAX_OCR_IMAGES_PER_PDF}. Pilih PDF yang lebih pendek."
        )
    return pdf_path, reference_path, len(reader.pages), ocr_image_count


def local_tesseract_text(
    png_image: bytes,
    executable: str,
    language: str,
    tessdata_prefix: str,
) -> str:
    try:
        process = subprocess.run(
            [executable, "--tessdata-dir", tessdata_prefix, "stdin", "stdout", "-l", language],
            input=png_image,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
            env=local_ocr_environment(),
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Tesseract lokal melewati batas waktu 60 detik.") from error
    except OSError as error:
        raise ValueError("Tesseract lokal tidak dapat dijalankan.") from error
    if process.returncode != 0:
        raise ValueError(
            f"Tesseract lokal gagal. Pastikan data bahasa '{language}' tersedia dan gambar sintetis dapat dibaca."
        )
    if len(process.stdout) > server.MAX_OCR_RESPONSE_BYTES:
        raise ValueError("Hasil OCR lokal melebihi batas 1 MiB untuk satu gambar.")
    return process.stdout.decode("utf-8", errors="replace")


def local_ocr_environment() -> dict[str, str]:
    """Pass only runtime-related environment values to local OCR processes."""
    allowed = (
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
        "LOCALAPPDATA", "PSMODULEPATH", "LANG", "LC_ALL", "TMPDIR",
    )
    return {key: os.environ[key] for key in allowed if os.environ.get(key)}


def local_windows_ocr_text(
    png_image: bytes,
    language_tag: str,
    executable_path: str | None = None,
    bridge_path: Path = WINDOWS_OCR_BRIDGE,
) -> str:
    """Run one normalized synthetic image through the offline Windows OCR API."""
    if os.name != "nt":
        raise ValueError("Windows OCR lokal hanya tersedia di Windows.")
    if (
        not isinstance(language_tag, str)
        or not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", language_tag)
    ):
        raise ValueError("Tag bahasa Windows OCR tidak valid.")
    if not bridge_path.is_file():
        raise ValueError("Bridge Windows OCR lokal tidak tersedia.")

    if executable_path:
        executable = Path(executable_path).expanduser()
    else:
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        executable = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise ValueError("Windows PowerShell 5.1 untuk Windows OCR tidak ditemukan.")

    script = bridge_path.read_text(encoding="utf-8-sig")
    encoded_script = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    child_environment = local_ocr_environment()
    child_environment["KARSAHIRE_WINDOWS_OCR_LANGUAGE"] = language_tag
    try:
        process = subprocess.run(
            [str(executable.resolve()), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_script],
            input=png_image,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            env=child_environment,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError("Windows OCR lokal melewati batas waktu 30 detik.") from error
    except OSError as error:
        raise ValueError("Windows OCR lokal tidak dapat dijalankan.") from error
    if process.returncode != 0:
        raise ValueError("Windows OCR lokal gagal; pastikan bahasa tersedia dan PNG dapat dibaca.")
    if len(process.stdout) > server.MAX_OCR_RESPONSE_BYTES:
        raise ValueError("Hasil Windows OCR lokal melebihi batas 1 MiB untuk satu gambar.")
    text = process.stdout.decode("utf-8", errors="replace")
    if not text.strip():
        raise ValueError("Windows OCR lokal tidak menghasilkan teks.")
    return text


def extract_with_local_windows_ocr(
    pdf_bytes: bytes,
    language_tag: str,
    executable_path: str | None = None,
    bridge_path: Path = WINDOWS_OCR_BRIDGE,
) -> tuple[list[tuple[int, str]], int, str, str]:
    """OCR only scanned pages in the selected synthetic PDF, without networking."""
    if os.name != "nt":
        raise ValueError("Windows OCR lokal hanya tersedia di Windows.")
    if not re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", language_tag):
        raise ValueError("Tag bahasa Windows OCR tidak valid.")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        page_lines: list[tuple[int, str]] = []
        image_count = 0
        processed_images = 0
        for page_num, page in enumerate(reader.pages, start=1):
            if (page.extract_text() or "").strip():
                continue
            for embedded in getattr(page, "images", []):
                image_count += 1
                if image_count > server.MAX_OCR_IMAGES_PER_PDF:
                    raise ValueError(
                        f"PDF melebihi batas {server.MAX_OCR_IMAGES_PER_PDF} gambar untuk Windows OCR lokal."
                    )
                try:
                    png_image = server.normalize_image(embedded.data)
                except ValueError:
                    continue
                text = local_windows_ocr_text(
                    png_image, language_tag, executable_path, bridge_path
                )
                processed_images += 1
                page_lines.extend((page_num, line) for line in text.splitlines() if line.strip())
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF sintetis tidak dapat diekstrak untuk Windows OCR lokal.") from error
    if image_count == 0:
        raise ValueError("PDF terpilih tidak memiliki gambar scan untuk Windows OCR lokal.")
    if not page_lines:
        raise ValueError("Windows OCR lokal tidak menghasilkan teks yang bisa dievaluasi.")
    os_build = platform.version() or "unknown"
    engine_version = f"Windows.Media.Ocr; system-managed model; Windows build {os_build}"
    return page_lines, processed_images, engine_version, file_sha256(bridge_path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_tessdata_prefix(
    executable: str,
    language: str,
    configured_directory: str | None = None,
) -> tuple[Path, str]:
    """Find and fingerprint the exact traineddata files used by this run."""
    if configured_directory:
        candidates = [Path(configured_directory).expanduser()]
    else:
        candidates = []
        environment_prefix = os.environ.get("TESSDATA_PREFIX")
        if environment_prefix:
            candidates.append(Path(environment_prefix).expanduser())
        executable_parent = Path(executable).resolve().parent
        candidates.extend((
            executable_parent,
            executable_parent.parent / "share",
            executable_parent.parent / "share" / "tesseract-ocr" / "5",
        ))

    languages = language.split("+")
    for raw_candidate in candidates:
        try:
            candidate = raw_candidate.resolve(strict=True)
            if not candidate.is_dir():
                continue
            # TESSDATA_PREFIX and --tessdata-dir use the parent of tessdata;
            # accept a direct tessdata path too and normalize it for the CLI.
            prefix = candidate.parent if candidate.name.casefold() == "tessdata" else candidate
            model_files = [prefix / "tessdata" / f"{code}.traineddata" for code in languages]
            if not all(path.is_file() for path in model_files):
                continue
            fingerprint = hashlib.sha256()
            for code, model_path in zip(languages, model_files):
                fingerprint.update(code.encode("ascii"))
                fingerprint.update(b"\0")
                fingerprint.update(file_sha256(model_path).encode("ascii"))
                fingerprint.update(b"\0")
            return prefix, fingerprint.hexdigest()
        except (OSError, UnicodeEncodeError):
            continue
    raise ValueError(
        f"Data bahasa Tesseract '{language}' tidak ditemukan. Berikan --tesseract-tessdata-dir "
        "ke folder yang berisi subfolder tessdata atau langsung ke folder tessdata."
    )


def extract_with_local_tesseract(
    pdf_bytes: bytes,
    language: str,
    executable_path: str | None = None,
    tessdata_directory: str | None = None,
) -> tuple[list[tuple[int, str]], int, str, str]:
    if executable_path:
        candidate = Path(executable_path).expanduser()
        if not candidate.is_file():
            raise ValueError("File executable Tesseract tidak ditemukan.")
        executable = str(candidate.resolve())
    else:
        executable = shutil.which("tesseract")
    if not executable:
        raise ValueError(
            "Tesseract tidak ditemukan di PATH. Pasang engine dan data bahasa secara lokal atau berikan --tesseract-executable."
        )
    if (
        not isinstance(language, str)
        or not re.fullmatch(r"[A-Za-z0-9_+.-]{1,64}", language)
        or language.startswith("-")
        or any(not code for code in language.split("+"))
    ):
        raise ValueError("Kode bahasa Tesseract tidak valid.")
    tessdata_prefix, language_data_sha256 = resolve_tessdata_prefix(
        executable, language, tessdata_directory
    )
    try:
        version_result = subprocess.run(
            [executable, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("Versi Tesseract lokal tidak dapat dibaca.") from error
    if version_result.returncode != 0:
        raise ValueError("Versi Tesseract lokal tidak dapat dibaca.")
    version_lines = version_result.stdout.decode("utf-8", errors="replace").splitlines()
    if not version_lines:
        raise ValueError("Tesseract lokal tidak melaporkan versi.")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        page_lines: list[tuple[int, str]] = []
        image_count = 0
        processed_images = 0
        for page_num, page in enumerate(reader.pages, start=1):
            if (page.extract_text() or "").strip():
                continue
            for embedded in getattr(page, "images", []):
                image_count += 1
                if image_count > server.MAX_OCR_IMAGES_PER_PDF:
                    raise ValueError(
                        f"PDF melebihi batas {server.MAX_OCR_IMAGES_PER_PDF} gambar untuk OCR lokal."
                    )
                try:
                    png_image = server.normalize_image(embedded.data)
                except ValueError:
                    continue
                text = local_tesseract_text(
                    png_image, executable, language, str(tessdata_prefix)
                )
                processed_images += 1
                page_lines.extend((page_num, line) for line in text.splitlines() if line.strip())
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("PDF sintetis tidak dapat diekstrak untuk OCR lokal.") from error
    if image_count == 0:
        raise ValueError("PDF terpilih tidak memiliki gambar scan untuk OCR lokal.")
    if not page_lines:
        raise ValueError("Tesseract lokal tidak menghasilkan teks yang bisa dievaluasi.")
    return page_lines, processed_images, version_lines[0][:120], language_data_sha256


def evaluate(
    sample_id: str,
    send_to_internal_ocr: bool = False,
    use_local_tesseract: bool = False,
    tesseract_language: str = "eng",
    tesseract_executable: str | None = None,
    tesseract_tessdata_dir: str | None = None,
    use_local_windows_ocr: bool = False,
    windows_ocr_language: str = "en-US",
    windows_ocr_executable: str | None = None,
) -> dict:
    selected_engines = sum((send_to_internal_ocr, use_local_tesseract, use_local_windows_ocr))
    if selected_engines > 1:
        raise ValueError("Pilih satu engine OCR untuk satu evaluasi.")
    pdf_path, reference_path, page_count, image_count = preflight(sample_id)
    manifest_bytes = resolve_dataset_file(DATASET / "manifest.json").read_bytes()
    pdf_bytes = pdf_path.read_bytes()
    reference_bytes = reference_path.read_bytes()
    evaluator_bytes = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    result = {
        "dataset": "synthetic-cv-32",
        "sample_id": sample_id,
        "pipeline_version": server.pipeline_version(),
        "ocr_model": server.OCR_MODEL,
        "dataset_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "sample_pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "reference_text_sha256": hashlib.sha256(reference_bytes).hexdigest(),
        "evaluator_sha256": hashlib.sha256(evaluator_bytes).hexdigest(),
        "pdf_pages": page_count,
        "ocr_images_planned": image_count,
        "ocr_requests_sent": 0,
        "network_mode": "disabled",
    }
    if not send_to_internal_ocr:
        if not use_local_tesseract and not use_local_windows_ocr:
            result["status"] = "preflight_only"
            result["note"] = "Tidak ada teks atau gambar yang dikirim ke layanan OCR."
            return result

    if use_local_tesseract:
        page_lines, processed_images, engine_version, language_data_sha256 = extract_with_local_tesseract(
            pdf_bytes, tesseract_language, tesseract_executable, tesseract_tessdata_dir
        )
        result.update({
            "network_mode": "disabled_local_tesseract",
            "ocr_model": None,
            "ocr_engine": "Tesseract",
            "ocr_engine_version": engine_version,
            "ocr_language": tesseract_language,
            "ocr_language_data_sha256": language_data_sha256,
            "ocr_images_processed": processed_images,
        })
    elif use_local_windows_ocr:
        page_lines, processed_images, engine_version, bridge_sha256 = extract_with_local_windows_ocr(
            pdf_bytes, windows_ocr_language, windows_ocr_executable
        )
        result.update({
            "network_mode": "disabled_local_windows_ocr",
            "ocr_model": None,
            "ocr_engine": "Windows.Media.Ocr",
            "ocr_engine_version": engine_version,
            "ocr_language": windows_ocr_language,
            "ocr_model_fingerprint": None,
            "ocr_model_revision": "Windows-managed; stable fingerprint unavailable",
            "ocr_bridge_sha256": bridge_sha256,
            "ocr_images_processed": processed_images,
        })
    else:
        if not server.ocr_is_configured():
            raise ValueError(
                f"Set {server.OCR_KEY_ENV}, {server.OCR_URL_ENV}, dan {server.OCR_ALLOWED_ORIGINS_ENV} "
                "ke nilai yang disetujui melalui environment sebelum memilih mode OCR."
            )

        _, page_lines = server.extract_document(pdf_path.name, pdf_bytes)
        result.update({
            "ocr_requests_sent": image_count,
            "network_mode": "internal_ocr_opt_in",
            "ocr_images_processed": image_count,
        })
    reference = reference_bytes.decode("utf-8")
    hypothesis = "\n".join(
        line for _, line in sorted(page_lines, key=lambda item: item[0] or 0)
    )
    edits, ref_count = word_error_counts(tokens(reference), tokens(hypothesis))
    result.update({
        "ocr_pages_returned": len({page for page, _ in page_lines if page is not None}),
        "reference_word_count": ref_count,
        "ocr_word_count": len(tokens(hypothesis)),
        "word_edits": edits,
        "word_error_rate": round(edits / ref_count, 4) if ref_count else None,
        "limitations": [
            "WER is compared with the corpus text reference, not human-adjudicated OCR ground truth.",
            "One synthetic English PDF does not establish OCR quality across layouts or languages.",
            "OCR output text is not printed or persisted by this script.",
        ],
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", required=True, help="Synthetic sample ID, for example r00003.")
    parser.add_argument(
        "--send-to-internal-ocr",
        action="store_true",
        help="Send this one sample's scan images to the configured internal OCR endpoint.",
    )
    parser.add_argument(
        "--local-tesseract",
        action="store_true",
        help="Run Tesseract on the local machine without sending images over the network.",
    )
    parser.add_argument(
        "--windows-ocr",
        action="store_true",
        help="Run the installed Windows OCR engine locally without network access.",
    )
    parser.add_argument(
        "--windows-ocr-language",
        default="en-US",
        help="Installed Windows OCR language tag (default: en-US).",
    )
    parser.add_argument(
        "--windows-ocr-executable",
        help="Optional path to Windows PowerShell 5.1 when it is not at its system location.",
    )
    parser.add_argument(
        "--tesseract-language",
        default="eng",
        help="Installed Tesseract language code for this synthetic sample (default: eng).",
    )
    parser.add_argument(
        "--tesseract-executable",
        help="Optional path to the local Tesseract executable when it is not on PATH.",
    )
    parser.add_argument(
        "--tesseract-tessdata-dir",
        help="Optional parent of the tessdata directory, or the tessdata directory itself.",
    )
    args = parser.parse_args()
    try:
        print(json.dumps(evaluate(
            args.sample_id,
            args.send_to_internal_ocr,
            args.local_tesseract,
            args.tesseract_language,
            args.tesseract_executable,
            args.tesseract_tessdata_dir,
            args.windows_ocr,
            args.windows_ocr_language,
            args.windows_ocr_executable,
        ), ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Synthetic OCR evaluation failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Local PDF/document tools. CPU-only; no cloud, no layout-reflow hacks."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from errors import ToolError
from paths import resolve_dir, resolve_existing_file, resolve_output_path, resolve_workspace


PDF_SUFFIX = {".pdf"}
PNG_SUFFIX = {".png"}
TEXT_SUFFIX = {".txt", ".md", ".html", ".odt", ".docx"}
LARGE_EDIT_CHARS = 400
DEFAULT_OCR_LANGS = "deu+eng"
RENDER_DPI = 140
MAX_TEXT_CHARS = 20000
QA_TEXT_CHARS = 1200
LIBREOFFICE_TIMEOUT = 120
OCR_TIMEOUT = 180
TESSDATA_DIR = Path.home() / ".local" / "share" / "tessdata"


def ensure_pdf_imports() -> None:
    """Allow the MCP venv to see user-site PyMuPDF/pikepdf/reportlab."""
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    extra = Path.home() / ".local" / "lib" / version / "site-packages"
    if extra.is_dir() and str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def capabilities() -> dict[str, Any]:
    ensure_pdf_imports()
    bins = {
        "qpdf": _which("qpdf"),
        "pdftoppm": _which("pdftoppm"),
        "pdftotext": _which("pdftotext"),
        "pdfunite": _which("pdfunite"),
        "pdfseparate": _which("pdfseparate"),
        "tesseract": _which("tesseract"),
        "ocrmypdf": _which("ocrmypdf"),
        "soffice": _which("soffice"),
    }
    mods: dict[str, str | None] = {}
    for name in ("pymupdf", "pikepdf", "reportlab", "ocrmypdf"):
        try:
            mod = __import__(name)
            mods[name] = getattr(mod, "__version__", "present")
        except Exception:
            mods[name] = None
    return {"binaries": bins, "python": mods, "tessdata_dir": str(TESSDATA_DIR) if TESSDATA_DIR.is_dir() else None}


def pdf_inspect(path: str) -> dict[str, Any]:
    ensure_pdf_imports()
    import pymupdf

    pdf = resolve_existing_file(path, PDF_SUFFIX)
    with pymupdf.open(pdf) as doc:
        pages = []
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            rect = page.rect
            pages.append(
                {
                    "page": index,
                    "width": round(rect.width, 2),
                    "height": round(rect.height, 2),
                    "has_text": bool(text.strip()),
                    "chars": len(text),
                }
            )
        result = {
            "ok": True,
            "path": str(pdf),
            "pages": doc.page_count,
            "is_encrypted": bool(doc.is_encrypted),
            "metadata": {key: value for key, value in (doc.metadata or {}).items() if value},
            "page_info": pages,
            "backend": "pymupdf",
        }
    return result


def pdf_read(path: str, pages: str = "", max_chars: int = MAX_TEXT_CHARS) -> dict[str, Any]:
    ensure_pdf_imports()
    import pymupdf

    pdf = resolve_existing_file(path, PDF_SUFFIX)
    limit = _clamp_int(max_chars, 1, MAX_TEXT_CHARS)
    with pymupdf.open(pdf) as doc:
        selected = _parse_pages(pages, doc.page_count)
        chunks: list[str] = []
        used = 0
        truncated = False
        for number in selected:
            text = doc[number - 1].get_text("text") or ""
            header = f"\n--- page {number} ---\n"
            remaining = limit - used
            if remaining <= 0:
                truncated = True
                break
            piece = header + text
            if len(piece) > remaining:
                piece = piece[:remaining]
                truncated = True
            chunks.append(piece)
            used += len(piece)
            if truncated:
                break
        result = {
            "ok": True,
            "path": str(pdf),
            "pages": doc.page_count,
            "read_pages": selected if not truncated else selected[: len(chunks)],
            "text": "".join(chunks).strip(),
            "chars": used,
            "truncated": truncated,
            "backend": "pymupdf",
        }
    return result


def pdf_create(
    output: str,
    text: str = "",
    source_path: str = "",
    title: str = "",
    workspace: str = "",
) -> dict[str, Any]:
    ensure_pdf_imports()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.enums import TA_LEFT
    from xml.sax.saxutils import escape

    dest = _output_pdf(output, workspace)
    body = text.strip() if isinstance(text, str) else ""
    if source_path.strip():
        src = resolve_existing_file(source_path, TEXT_SUFFIX | PDF_SUFFIX)
        if src.suffix.lower() in PDF_SUFFIX:
            raise ToolError("pdf_create erwartet Text oder eine Textdatei, kein PDF als Quelle.")
        body = src.read_text(encoding="utf-8")
    if not body.strip():
        raise ToolError("pdf_create braucht text oder source_path mit Inhalt.")
    heading = title.strip() or dest.stem
    styles = getSampleStyleSheet()
    title_style = styles["Heading1"]
    body_style = styles["BodyText"]
    body_style.alignment = TA_LEFT
    story: list[Any] = [Paragraph(escape(heading), title_style), Spacer(1, 6 * mm)]
    for block in body.split("\n"):
        line = escape(block) if block.strip() else "&nbsp;"
        story.append(Paragraph(line, body_style))
    doc = SimpleDocTemplate(str(dest), pagesize=A4, title=heading)
    doc.build(story)
    qa = qa_pdf(str(dest))
    return {"ok": True, "path": str(dest), "backend": "reportlab", "qa": qa}


def pdf_edit(
    path: str,
    output: str,
    replacements: str = "",
    new_text: str = "",
    mode: str = "auto",
    workspace: str = "",
) -> dict[str, Any]:
    """Edit a PDF. mode=replace keeps layout; recreate/soffice rebuild from text."""
    ensure_pdf_imports()
    import pymupdf

    src = resolve_existing_file(path, PDF_SUFFIX)
    dest = _output_pdf(output, workspace)
    parsed = _parse_replacements(replacements)
    chosen = (mode or "auto").strip().lower()
    if chosen not in {"auto", "replace", "recreate", "soffice"}:
        raise ToolError("mode muss auto, replace, recreate oder soffice sein.")

    # Layout-safe default: with replacements only, prefer in-place replace.
    # Recreate ONLY when explicitly requested or when new_text is provided.
    # (Old auto used total_delta >= 400 and destroyed tables/logos on multi-field edits.)
    use_recreate = chosen in {"recreate", "soffice"} or bool(new_text.strip())
    if chosen == "replace":
        use_recreate = False
    if chosen == "auto" and parsed and not new_text.strip():
        use_recreate = False
    if use_recreate:
        if new_text.strip():
            body = new_text.strip()
        else:
            with pymupdf.open(src) as doc:
                body = "\n".join((page.get_text("text") or "") for page in doc)
            for item in parsed:
                body = body.replace(item["find"], item["replace"])
        if chosen == "soffice":
            result = _recreate_via_soffice(body, dest, title=src.stem)
        else:
            result = pdf_create(str(dest), text=body, title=src.stem)
        result["mode"] = "recreate-soffice" if chosen == "soffice" else "recreate-text"
        result["source"] = str(src)
        result["note"] = (
            "Große Textänderung: neues PDF aus Zwischenformat, kein blindes PDF-Reflow."
        )
        return result

    if not parsed:
        raise ToolError("pdf_edit ohne new_text braucht replacements wie 'alt=>neu;foo=>bar'.")

    # Prefer content-stream byte replace for same-length pairs (keeps PDFlib
    # geometry / fonts / small header tables). Redaction rewrites glyphs and
    # often shifts columns or drops right-side totals.
    same_len = [p for p in parsed if len(p["find"]) == len(p["replace"])]
    diff_len = [p for p in parsed if len(p["find"]) != len(p["replace"])]
    stream_hits = 0
    if same_len:
        stream_hits = _replace_in_content_streams(src, dest, same_len)
    else:
        shutil.copy2(src, dest)

    replaced = stream_hits
    redact_hits = 0
    # Redact only different-length pairs, or everything if stream found nothing.
    targets = diff_len if stream_hits else parsed
    if targets:
        with pymupdf.open(dest) as doc:
            for page in doc:
                page_hits = 0
                for item in targets:
                    hits = page.search_for(item["find"])
                    for rect in hits:
                        fs = 11.0
                        try:
                            for block in page.get_text("dict").get("blocks", []):
                                if block.get("type") != 0:
                                    continue
                                for line in block.get("lines", []):
                                    for span in line.get("spans", []):
                                        sb = span.get("bbox")
                                        if not sb:
                                            continue
                                        if pymupdf.Rect(sb).intersects(rect):
                                            fs = min(fs, float(span.get("size") or fs))
                        except Exception:
                            pass
                        page.add_redact_annot(
                            rect,
                            text=item["replace"],
                            fontsize=fs,
                            fill=(1, 1, 1),
                            text_color=(0, 0, 0),
                            cross_out=False,
                        )
                        redact_hits += 1
                        page_hits += 1
                if page_hits:
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
            if redact_hits:
                doc.saveIncr()
                replaced += redact_hits

    if replaced == 0:
        raise ToolError(
            "Kein Treffer für die angegebenen replacements — PDF unverändert. "
            f"Gesucht: {[item['find'] for item in parsed]}"
        )
    qa = qa_pdf(str(dest))
    backend = (
        "pikepdf-stream"
        if stream_hits and not redact_hits
        else ("pikepdf-stream+pymupdf" if stream_hits else "pymupdf")
    )
    return {
        "ok": True,
        "path": str(dest),
        "source": str(src),
        "mode": "replace",
        "replacements_applied": replaced,
        "stream_hits": stream_hits,
        "redact_hits": redact_hits,
        "backend": backend,
        "qa": qa,
    }


def pdf_merge(paths: str, output: str, workspace: str = "") -> dict[str, Any]:
    ensure_pdf_imports()
    import pikepdf

    sources = [resolve_existing_file(item.strip(), PDF_SUFFIX) for item in paths.split(",") if item.strip()]
    if len(sources) < 2:
        raise ToolError("pdf_merge braucht mindestens zwei PDF-Pfade, kommagetrennt.")
    dest = _output_pdf(output, workspace)
    merged = pikepdf.Pdf.new()
    for src in sources:
        with pikepdf.open(src) as src_pdf:
            merged.pages.extend(src_pdf.pages)
    merged.save(dest)
    qa = qa_pdf(str(dest))
    return {
        "ok": True,
        "path": str(dest),
        "sources": [str(item) for item in sources],
        "backend": "pikepdf",
        "qa": qa,
    }


def pdf_split(path: str, output_dir: str, pages: str = "", workspace: str = "") -> dict[str, Any]:
    ensure_pdf_imports()
    import pikepdf

    src = resolve_existing_file(path, PDF_SUFFIX)
    if workspace.strip():
        resolve_workspace(workspace)
    dest_dir = resolve_dir(output_dir, create=True)
    created: list[str] = []
    with pikepdf.open(src) as src_pdf:
        selected = _parse_pages(pages, len(src_pdf.pages))
        if pages.strip():
            out = pikepdf.Pdf.new()
            for number in selected:
                out.pages.append(src_pdf.pages[number - 1])
            dest = dest_dir / f"{src.stem}-pages-{_page_slug(selected)}.pdf"
            out.save(dest)
            created.append(str(dest))
        else:
            for index, page in enumerate(src_pdf.pages, start=1):
                out = pikepdf.Pdf.new()
                out.pages.append(page)
                dest = dest_dir / f"{src.stem}-p{index:03d}.pdf"
                out.save(dest)
                created.append(str(dest))
    qa = qa_pdf(created[0]) if created else {"ok": False, "errors": ["Kein Output"]}
    return {
        "ok": True,
        "source": str(src),
        "outputs": created,
        "count": len(created),
        "backend": "pikepdf",
        "qa": qa,
    }


def pdf_ocr(path: str, output: str, languages: str = DEFAULT_OCR_LANGS, workspace: str = "") -> dict[str, Any]:
    src = resolve_existing_file(path, PDF_SUFFIX)
    dest = _output_pdf(output, workspace)
    ocrmypdf_bin = _which("ocrmypdf")
    tesseract_bin = _which("tesseract")
    if not ocrmypdf_bin or not tesseract_bin:
        return {
            "ok": False,
            "callable": True,
            "path": str(src),
            "error": "OCR-Pipeline ist registriert, aber ocrmypdf oder tesseract fehlt im PATH.",
            "missing": [
                name
                for name, present in (("ocrmypdf", ocrmypdf_bin), ("tesseract", tesseract_bin))
                if not present
            ],
        }
    langs = languages.strip() or DEFAULT_OCR_LANGS
    tessdir = TESSDATA_DIR if TESSDATA_DIR.is_dir() else Path("/usr/share/tesseract/tessdata")
    env = _tool_env()
    cmd = [
        ocrmypdf_bin,
        "--output-type",
        "pdf",
        "--language",
        langs,
        "--skip-text",
        "--optimize",
        "0",
        str(src),
        str(dest),
    ]
    try:
        with tempfile.TemporaryDirectory(prefix="local-ai-ocr-") as tmp:
            wrapper = Path(tmp) / "tesseract"
            wrapper.write_text(
                "#!/bin/sh\n"
                f'exec "{tesseract_bin}" --tessdata-dir "{tessdir}" "$@"\n',
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            env["PATH"] = str(Path(tmp)) + os.pathsep + env.get("PATH", "")
            env.pop("TESSDATA_PREFIX", None)
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=OCR_TIMEOUT,
                env=env,
            )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"ocr Timeout nach {OCR_TIMEOUT}s") from exc
    if completed.returncode != 0 or not dest.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
        return {
            "ok": False,
            "callable": True,
            "path": str(src),
            "error": f"ocrmypdf exit {completed.returncode}",
            "detail": detail,
            "backend": "ocrmypdf",
        }
    qa = qa_pdf(str(dest))
    return {
        "ok": True,
        "path": str(dest),
        "source": str(src),
        "languages": langs,
        "backend": "ocrmypdf+tesseract",
        "qa": qa,
    }


def pdf_render(path: str, output: str, page: int = 1, dpi: int = RENDER_DPI, workspace: str = "") -> dict[str, Any]:
    ensure_pdf_imports()
    import pymupdf

    src = resolve_existing_file(path, PDF_SUFFIX)
    dest = resolve_output_path(output, PNG_SUFFIX)
    if workspace.strip():
        resolve_workspace(workspace)
    with pymupdf.open(src) as doc:
        index = _clamp_int(page, 1, doc.page_count)
        pix = doc[index - 1].get_pixmap(dpi=_clamp_int(dpi, 36, 300))
        pix.save(dest)
        result = {
            "ok": True,
            "path": str(dest),
            "source": str(src),
            "page": index,
            "pages": doc.page_count,
            "dpi": _clamp_int(dpi, 36, 300),
            "width": pix.width,
            "height": pix.height,
            "backend": "pymupdf",
            "vision": {
                "ready": True,
                "page": index,
                "image_path": str(dest),
                "mime": "image/png",
                "note": "Kein Vision-Modell aufgerufen. PNG ist für spätere visuelle QA.",
            },
        }
    return result


def qa_pdf(path: str, render_page: int = 1) -> dict[str, Any]:
    """Re-open a PDF, check pages/text, render one page. Vision-ready, no vision call."""
    ensure_pdf_imports()
    import pymupdf

    errors: list[str] = []
    warnings: list[str] = []
    pdf = Path(path)
    if not pdf.is_file():
        return {"ok": False, "errors": [f"QA: Datei fehlt: {pdf}"]}
    render_path = pdf.with_name(f"{pdf.stem}.qa-p{render_page}.png")
    try:
        with pymupdf.open(pdf) as doc:
            pages = doc.page_count
            if pages < 1:
                errors.append("PDF hat keine Seiten.")
            if doc.is_encrypted:
                errors.append("PDF ist verschlüsselt.")
            text_parts: list[str] = []
            for page in doc:
                text_parts.append(page.get_text("text") or "")
            text = "\n".join(text_parts)
            index = min(max(int(render_page), 1), max(pages, 1))
            try:
                pix = doc[index - 1].get_pixmap(dpi=RENDER_DPI)
                pix.save(render_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Render fehlgeschlagen: {exc}")
                render_path = None
            if pages > 0 and not text.strip():
                warnings.append("Kein extrahierbarer Text. OCR oder Scan-PDF möglich.")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"QA: PDF ließ sich nicht öffnen: {exc}"]}
    return {
        "ok": not errors,
        "path": str(pdf),
        "pages": pages if "pages" in locals() else 0,
        "text_chars": len(text) if "text" in locals() else 0,
        "text_preview": (text[:QA_TEXT_CHARS] if "text" in locals() else ""),
        "render_path": str(render_path) if render_path else None,
        "errors": errors,
        "warnings": warnings,
        "vision": {
            "ready": bool(render_path) and not errors,
            "page": render_page,
            "image_path": str(render_path) if render_path else None,
            "mime": "image/png",
            "note": "Kein Vision-Modell aufgerufen. Render liegt bereit.",
        },
    }


def make_image_only_pdf(path: str, output: str, page: int = 1, dpi: int = 150) -> dict[str, Any]:
    """Rasterize a page into a new PDF without a text layer. Used by OCR smoke tests."""
    ensure_pdf_imports()
    import pymupdf

    src = resolve_existing_file(path, PDF_SUFFIX)
    dest = resolve_output_path(output, PDF_SUFFIX)
    with pymupdf.open(src) as doc:
        index = _clamp_int(page, 1, doc.page_count)
        src_page = doc[index - 1]
        pix = src_page.get_pixmap(dpi=_clamp_int(dpi, 72, 300))
        out = pymupdf.open()
        new_page = out.new_page(width=src_page.rect.width, height=src_page.rect.height)
        new_page.insert_image(new_page.rect, stream=pix.tobytes("png"))
        out.save(dest)
        out.close()
    return {"ok": True, "path": str(dest), "source": str(src)}


def _recreate_via_soffice(text: str, dest: Path, title: str) -> dict[str, Any]:
    soffice = _which("soffice")
    if not soffice:
        raise ToolError("LibreOffice (soffice) ist nicht im PATH.")
    with tempfile.TemporaryDirectory(prefix="local-ai-lo-") as tmp:
        tmp_dir = Path(tmp)
        source = tmp_dir / f"{title or 'document'}.txt"
        source.write_text(f"{title}\n\n{text}", encoding="utf-8")
        profile = tmp_dir / "lo-profile"
        cmd = [
            soffice,
            "--headless",
            "--nologo",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmp_dir),
            str(source),
        ]
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=LIBREOFFICE_TIMEOUT,
            env=_tool_env(),
        )
        produced = tmp_dir / f"{source.stem}.pdf"
        if completed.returncode != 0 or not produced.is_file():
            detail = (completed.stderr or completed.stdout or "").strip()[-800:]
            raise ToolError(f"LibreOffice konnte kein PDF erzeugen. {detail}")
        shutil.copy2(produced, dest)
    qa = qa_pdf(str(dest))
    return {"ok": True, "path": str(dest), "backend": "libreoffice", "qa": qa}


def _output_pdf(output: str, workspace: str) -> Path:
    if workspace.strip():
        resolve_workspace(workspace)
    return resolve_output_path(output, PDF_SUFFIX)


def _parse_pages(spec: str, page_count: int) -> list[int]:
    if page_count < 1:
        raise ToolError("PDF hat keine Seiten.")
    raw = (spec or "").strip()
    if not raw:
        return list(range(1, page_count + 1))
    selected: list[int] = []
    try:
        parts = raw.split(",")
    except Exception:
        parts = []
    for part in parts:
        item = part.strip()
        if not item:
            continue
        try:
            if "-" in item:
                start_s, end_s = item.split("-", 1)
                start, end = int(start_s), int(end_s)
            else:
                start = end = int(item)
        except ValueError as exc:
            raise ToolError(f"Ungültige Seitenangabe: {item}") from exc
        if start > end:
            start, end = end, start
        for number in range(start, end + 1):
            if not 1 <= number <= page_count:
                raise ToolError(f"Seite {number} liegt außerhalb 1..{page_count}.")
            if number not in selected:
                selected.append(number)
    if not selected:
        raise ToolError("Keine gültigen Seiten in pages.")
    return selected


def _replace_in_content_streams(src: Path, dest: Path, pairs: list[dict[str, str]]) -> int:
    """Same-length literal replace inside page content streams (layout-safe)."""
    ensure_pdf_imports()
    import pikepdf

    shutil.copy2(src, dest)
    # Longest first so multi-field lines win over short amount tokens.
    ordered = sorted(pairs, key=lambda p: -len(p["find"]))
    encoded: list[tuple[bytes, bytes]] = []
    for item in ordered:
        try:
            encoded.append((item["find"].encode("latin-1"), item["replace"].encode("latin-1")))
        except UnicodeEncodeError as exc:
            raise ToolError(
                "Stream-Replace braucht latin-1-Text gleicher Länge (PDF-Inhaltsstrom)."
            ) from exc
        if len(encoded[-1][0]) != len(encoded[-1][1]):
            raise ToolError("Intern: Stream-Replace nur bei gleicher Byte-Länge.")

    hits = 0
    with pikepdf.open(dest, allow_overwriting_input=True) as pdf:
        for page in pdf.pages:
            contents = page.get("/Contents")
            if contents is None:
                continue
            streams = list(contents) if isinstance(contents, pikepdf.Array) else [contents]
            for st in streams:
                data = bytearray(st.read_bytes())
                for old, new in encoded:
                    start = 0
                    while True:
                        idx = data.find(old, start)
                        if idx < 0:
                            break
                        data[idx : idx + len(old)] = new
                        hits += 1
                        start = idx + len(new)
                st.write(bytes(data))
        pdf.save(dest)
    return hits


def _parse_replacements(raw: str) -> list[dict[str, str]]:
    text = (raw or "").strip()
    if not text:
        return []
    pairs: list[dict[str, str]] = []
    for chunk in text.split(";"):
        item = chunk.strip()
        if not item:
            continue
        if "=>" not in item:
            raise ToolError("replacements Format: 'alt=>neu;foo=>bar'")
        find, replace = item.split("=>", 1)
        if not find:
            raise ToolError("Leerer Suchtext in replacements.")
        pairs.append({"find": find, "replace": replace})
    return pairs


def _page_slug(pages: list[int]) -> str:
    if len(pages) == 1:
        return str(pages[0])
    return f"{pages[0]}-{pages[-1]}"


def _clamp_int(value: int | str, minimum: int, maximum: int) -> int:
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError("Zahl erwartet.")
    return max(minimum, min(maximum, value))


def _which(name: str) -> str | None:
    env_path = _tool_env()["PATH"]
    found = shutil.which(name, path=env_path)
    return found


def _tool_env() -> dict[str, str]:
    env = os.environ.copy()
    local_bin = str(Path.home() / ".local" / "bin")
    env["PATH"] = os.pathsep.join([local_bin, env.get("PATH", "")])
    return env

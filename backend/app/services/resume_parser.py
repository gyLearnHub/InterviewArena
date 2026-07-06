import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from docx import Document
from fastapi import status
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import AppError, ErrorCode
from app.core.http_status import HTTP_422_UNPROCESSABLE_CONTENT
from app.schemas.resume import StructuredResumeData
from app.services.llm import LLMClient

MAX_RESUME_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".doc", ".docx"}

ProjectConverter = Callable[[Path, Path], Path]


class ResumeParserService:
    def __init__(
        self,
        llm_client: LLMClient,
        settings: Settings | None = None,
        converter: ProjectConverter | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.settings = settings or get_settings()
        self.converter = converter or convert_doc_to_docx

    def parse(self, original_path: Path) -> dict[str, Any]:
        if original_path.suffix.lower() == ".doc":
            with tempfile.TemporaryDirectory(
                dir=original_path.parent,
                prefix=f"{original_path.stem}-converted-",
            ) as temp_dir:
                parse_path = self.converter(original_path, Path(temp_dir))
                _validate_converted_path(parse_path, Path(temp_dir))
                resume_text = extract_docx_text(parse_path)
        else:
            resume_text = extract_docx_text(original_path)

        if not resume_text.strip():
            raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)
        _validate_resume_text_length(resume_text, self.settings.resume_max_text_chars)

        structured_data = self.llm_client.parse_resume(resume_text)
        try:
            return StructuredResumeData.model_validate(structured_data).model_dump()
        except ValidationError as exc:
            raise AppError(
                ErrorCode.RESUME_PARSE_FAILED,
                HTTP_422_UNPROCESSABLE_CONTENT,
            ) from exc


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_upload_dir(settings: Settings | None = None) -> Path:
    configured = Path((settings or get_settings()).upload_dir)
    if not configured.is_absolute():
        configured = project_root() / configured
    return configured


def validate_resume_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(ErrorCode.INVALID_UPLOAD_TYPE, status.HTTP_400_BAD_REQUEST)
    return extension


def make_resume_path(filename: str, upload_dir: Path) -> Path:
    extension = validate_resume_extension(filename)
    safe_stem = Path(filename).stem.strip().replace(" ", "_") or "resume"
    candidate = upload_dir / f"{safe_stem}{extension}"
    counter = 1
    while candidate.exists():
        candidate = upload_dir / f"{safe_stem}_{counter}{extension}"
        counter += 1
    return candidate


def extract_docx_text(path: Path) -> str:
    try:
        document = Document(str(path))
    except Exception as exc:
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT) from exc

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                paragraphs.append("\t".join(cells))
    text = "\n".join(paragraphs)
    if text.strip():
        return text
    return extract_docx_xml_text(path)


def extract_docx_xml_text(path: Path) -> str:
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    xml_parts = (
        "word/document.xml",
        "word/header1.xml",
        "word/header2.xml",
        "word/header3.xml",
        "word/footer1.xml",
        "word/footer2.xml",
        "word/footer3.xml",
    )
    paragraphs: list[str] = []

    try:
        with zipfile.ZipFile(path) as archive:
            for part_name in xml_parts:
                if part_name not in archive.namelist():
                    continue
                root = ElementTree.fromstring(archive.read(part_name))
                for paragraph in root.findall(".//w:p", namespaces):
                    if paragraph.findall(".//w:p", namespaces):
                        continue
                    text = "".join(
                        node.text or ""
                        for node in paragraph.findall(".//w:t", namespaces)
                    ).strip()
                    if text:
                        paragraphs.append(text)
    except (ElementTree.ParseError, OSError, zipfile.BadZipFile) as exc:
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT) from exc

    return "\n".join(paragraphs)


def _validate_resume_text_length(resume_text: str, max_chars: int) -> None:
    if len(resume_text) <= max(1, max_chars):
        return
    raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)


def _validate_converted_path(path: Path, output_dir: Path) -> None:
    try:
        converted_path = path.resolve(strict=True)
        converted_root = output_dir.resolve(strict=True)
    except OSError as exc:
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT) from exc
    if (
        converted_path.suffix.lower() != ".docx"
        or not converted_path.is_relative_to(converted_root)
    ):
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)


def convert_doc_to_docx(input_path: Path, output_dir: Path) -> Path:
    libreoffice = shutil.which("libreoffice") or shutil.which("soffice")
    if libreoffice is None:
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.docx"
    if output_path.exists():
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)
    try:
        subprocess.run(
            [
                libreoffice,
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(output_dir),
                str(input_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(1, get_settings().resume_conversion_timeout_seconds),
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT) from exc

    if not output_path.exists():
        raise AppError(ErrorCode.RESUME_PARSE_FAILED, HTTP_422_UNPROCESSABLE_CONTENT)
    return output_path

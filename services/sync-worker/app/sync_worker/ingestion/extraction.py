from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from pypdf import PdfReader


class UnsupportedFileTypeError(ValueError):
    pass


@dataclass(slots=True)
class ExtractedContent:
    text: str
    extractor_name: str
    metadata: dict[str, str] = field(default_factory=dict)


class CompositeFileExtractor:
    def extract(self, file_name: str, content: bytes, mime_type: str | None = None) -> ExtractedContent:
        extension = PurePosixPath(file_name).suffix.lower()
        if extension == ".txt":
            return self._extract_txt(content)
        if extension == ".pdf":
            return self._extract_pdf(content)
        if extension == ".docx":
            return self._extract_docx(content)
        if extension == ".pptx":
            return self._extract_pptx(content)
        raise UnsupportedFileTypeError(f"Unsupported file type: {file_name}")

    def _extract_txt(self, content: bytes) -> ExtractedContent:
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                text = content.decode(encoding)
                return ExtractedContent(text=text, extractor_name="plain-text", metadata={"encoding": encoding})
            except UnicodeDecodeError:
                continue
        text = content.decode("utf-8", errors="ignore")
        return ExtractedContent(text=text, extractor_name="plain-text", metadata={"encoding": "utf-8-ignore"})

    def _extract_pdf(self, content: bytes) -> ExtractedContent:
        reader = PdfReader(BytesIO(content))
        page_text = []
        for page in reader.pages:
            page_text.append(page.extract_text() or "")
        return ExtractedContent(text="\n".join(page_text).strip(), extractor_name="pypdf")

    def _extract_docx(self, content: bytes) -> ExtractedContent:
        with ZipFile(BytesIO(content)) as archive:
            xml_payload = archive.read("word/document.xml")
        root = ET.fromstring(xml_payload)
        namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text_parts = [node.text for node in root.findall(".//w:t", namespaces) if node.text]
        return ExtractedContent(text="\n".join(text_parts).strip(), extractor_name="docx-xml")

    def _extract_pptx(self, content: bytes) -> ExtractedContent:
        with ZipFile(BytesIO(content)) as archive:
            slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            text_parts: list[str] = []
            namespaces = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for slide_name in slide_names:
                root = ET.fromstring(archive.read(slide_name))
                text_parts.extend(node.text for node in root.findall(".//a:t", namespaces) if node.text)
        return ExtractedContent(text="\n".join(text_parts).strip(), extractor_name="pptx-xml")

"""A minimal, dependency-free Word document writer.

Novellire's export is plain prose and headings, so a small WordprocessingML
package covers it without adding a document library or touching the network.
The zip holds the minimum Word expects: content types, package relationships, a
document part, its styles relationship, and the styles themselves.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

_PACKAGE_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/>
<w:rPr><w:sz w:val="22"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Title">
<w:name w:val="Title"/><w:basedOn w:val="Normal"/>
<w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="56"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Subtitle">
<w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/>
<w:pPr><w:jc w:val="center"/><w:spacing w:after="120"/></w:pPr>
<w:rPr><w:i/><w:color w:val="555555"/><w:sz w:val="24"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Heading1">
<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="480" w:after="200"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="40"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="Heading2">
<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
</w:style>
<w:style w:type="paragraph" w:styleId="WordCount">
<w:name w:val="Word count"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="200"/></w:pPr>
<w:rPr><w:i/><w:color w:val="666666"/><w:sz w:val="18"/></w:rPr>
</w:style>
</w:styles>"""

_STYLE_IDS = {
    "title": "Title",
    "subtitle": "Subtitle",
    "summary": "WordCount",
    "part": "Heading1",
    "documents": "Heading1",
    "chapter": "Heading2",
    "document": "Heading2",
    "words": "WordCount",
    "body": "Normal",
}


def build_docx(entries: list[tuple[str, str]]) -> bytes:
    """Build a .docx package from ``(style, text)`` entries.

    Styles are the keys of ``_STYLE_IDS``; unknown keys fall back to Normal.
    Each entry is one paragraph, with blank lines inside body text splitting it
    into separate paragraphs.
    """
    paragraphs: list[str] = []
    for style, text in entries:
        cleaned = (text or "").replace("\r\n", "\n").strip()
        if not cleaned:
            continue
        if style == "body":
            for block in cleaned.split("\n\n"):
                block = " ".join(block.split())
                if block:
                    paragraphs.append(_paragraph("Normal", block))
            continue
        paragraphs.append(
            _paragraph(_STYLE_IDS.get(style, "Normal"), " ".join(cleaned.split()))
        )

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'
        "</w:sectPr></w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in (
            ("[Content_Types].xml", _CONTENT_TYPES),
            ("_rels/.rels", _PACKAGE_RELS),
            ("word/document.xml", document),
            ("word/_rels/document.xml.rels", _DOCUMENT_RELS),
            ("word/styles.xml", _STYLES),
        ):
            archive.writestr(
                zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content
            )
    return buffer.getvalue()


def _paragraph(style_id: str, text: str) -> str:
    return (
        "<w:p>"
        f'<w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>'
        f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'
        "</w:p>"
    )

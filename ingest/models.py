from dataclasses import dataclass


@dataclass
class IngestResult:
    title: str
    text: str
    source_type: str
    source_label: str
    article_date: str = ""

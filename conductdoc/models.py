# conductdoc/models.py
"""🧱 Core data structures for representing code and analysis results."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

@dataclass
class CodeElement:
    name: str
    type: str
    filepath: Path
    lineno_start: int
    lineno_end: int
    source_code: str
    docstring: str
    ai_documentation: Dict[str, str] = field(default_factory=dict)
    
    @property
    def html_filename(self) -> str:
        safe_path = str(self.filepath).replace("/", "_").replace("\\", "_")
        return f"{safe_path}_{self.name}.html"

@dataclass
class AnalysisResult:
    summary: str
    architecture_diagram: str
    examples: Dict[str, str]
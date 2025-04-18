from pydantic import BaseModel
from typing import List, Optional


class CodeSnippet(BaseModel):
    before: Optional[str]
    after: Optional[str]
    explanation: str


class ChangeDetail(BaseModel):
    function_name: Optional[str]
    summary: str
    purpose: str
    impact: str
    snippets: List[CodeSnippet]


class FileChange(BaseModel):
    file_path: str
    description: str
    changes: List[ChangeDetail]
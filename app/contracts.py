from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AskRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)
    language: Literal['fa', 'en'] = 'fa'

    @model_validator(mode='after')
    def clean(self):
        self.question = self.question.strip()
        if len(self.question) < 3:
            raise ValueError('Question must have at least three non-space characters.')
        if any(ord(c) < 32 and c not in '\n\t' for c in self.question):
            raise ValueError('Control characters are not permitted.')
        return self


class Plan(StrictModel):
    route: Literal['documents', 'database', 'hybrid', 'calculator', 'clarify']
    document_question: str | None
    database_question: str | None
    needs_calculator: bool
    calculation_goal: str | None
    clarification: str | None

    @model_validator(mode='after')
    def coherent(self):
        if (self.route in {'documents', 'hybrid'}) != bool(self.document_question):
            raise ValueError('Document routing and question disagree.')
        if (self.route in {'database', 'hybrid'}) != bool(self.database_question):
            raise ValueError('Database routing and question disagree.')
        if self.needs_calculator != bool(self.calculation_goal):
            raise ValueError('Calculator requires a calculation goal.')
        if self.route == 'calculator' and not self.needs_calculator:
            raise ValueError('Calculator route must call the calculator.')
        if self.route == 'clarify' and (not self.clarification or self.needs_calculator):
            raise ValueError('Clarification route cannot execute tools.')
        return self


class Citation(StrictModel):
    source_id: str
    quote: str


class NumericFact(StrictModel):
    name: str
    value: str
    source_id: str
    quote: str


class DocumentAnswer(StrictModel):
    sufficient: bool
    answer: str
    citations: list[Citation]
    numeric_facts: list[NumericFact]


class SQLDraft(StrictModel):
    answerable: bool
    sql: str | None
    parameters: list[str | int | float | None]
    explanation: str


class FinalAnswer(StrictModel):
    answer: str
    used_source_ids: list[str]
    used_sql_ids: list[str]
    used_calculation: bool


class CalculatorArguments(StrictModel):
    expression: str = Field(min_length=1, max_length=256)
    precision: int = Field(ge=0, le=6)


class AskResponse(StrictModel):
    request_id: str
    status: Literal['answered', 'insufficient_evidence', 'clarification_required']
    answer: str
    route: str
    sources: list[dict[str, Any]]
    sql: list[dict[str, Any]]
    calculations: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    warnings: list[str]

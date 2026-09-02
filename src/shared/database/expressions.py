from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


class normalized_timestamp(FunctionElement):
    """Convert persisted ISO timestamp text to a comparable database timestamp."""

    inherit_cache = True
    name = "normalized_timestamp"


@compiles(normalized_timestamp)
def _compile_default(element, compiler, **kwargs):
    argument = compiler.process(list(element.clauses)[0], **kwargs)
    return f"CAST({argument} AS TIMESTAMP)"


@compiles(normalized_timestamp, "postgresql")
def _compile_postgresql(element, compiler, **kwargs):
    argument = compiler.process(list(element.clauses)[0], **kwargs)
    return f"CAST({argument} AS TIMESTAMPTZ)"


@compiles(normalized_timestamp, "sqlite")
def _compile_sqlite(element, compiler, **kwargs):
    argument = compiler.process(list(element.clauses)[0], **kwargs)
    return f"datetime({argument})"

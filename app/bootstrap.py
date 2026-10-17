from .config import Settings
from .seed import seed_database
from .llm import OpenAIProvider, GeminiProvider
from .retrieval import build_retriever
from .tools.database import ReadOnlySQL
from .agents.document_agent import DocumentAgent
from .agents.database_agent import DatabaseAgent
from .coordinator import Coordinator


def bootstrap(settings: Settings):
    seed_database(settings.data_dir, settings.db_path)
    provider = GeminiProvider(settings) if settings.provider == 'gemini' else OpenAIProvider(settings)
    try:
        retriever = build_retriever(settings, provider)
        database = ReadOnlySQL(settings.db_path, settings.sql_max_rows,
                               settings.sql_timeout_seconds, settings.sql_vm_steps)
        coordinator = Coordinator(provider, DocumentAgent(provider, retriever), DatabaseAgent(provider, database))
        return coordinator, provider
    except Exception:
        provider.close()
        raise


if __name__ == '__main__':
    coordinator, provider = bootstrap(Settings())
    print('Database and real semantic index are ready.')
    provider.close()

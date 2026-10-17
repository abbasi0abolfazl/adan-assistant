"""Direct HTTP adapter for the documented OpenAI Responses and Embeddings APIs.

No mock/fallback/provider impersonation exists in runtime code. Test doubles live in tests/.
"""
import json
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable
import httpx
from pydantic import BaseModel, ValidationError
from .config import Settings
from .errors import AppError
from .trace import Trace

T = TypeVar('T', bound=BaseModel)


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol declaring the contract required of all LLM provider adapters."""

    def structured(self, instructions: str, payload: dict, model: type[T], trace: Trace) -> T:
        ...

    def choose_calculator(
        self, instructions: str, payload: dict, argument_model: type[BaseModel], trace: Trace
    ) -> 'ToolTurn':
        ...

    def complete_tool(
        self, turn: 'ToolTurn', result: dict, instructions: str, model: type[T], trace: Trace
    ) -> T:
        ...

    def embed(self, texts: list[str], trace: Trace | None = None) -> list[list[float]]:
        ...

    def close(self) -> None:
        ...


@dataclass
class ToolTurn:
    call_id: str
    name: str
    arguments: dict
    transcript: list[dict]
    instructions: str


class OpenAIProvider:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        key = settings.active_api_key.get_secret_value()
        if not key:
            variable = 'GEMINI_API_KEY' if settings.provider == 'gemini' else 'OPENAI_API_KEY'
            raise AppError('CONFIG_MISSING', f'Set {variable} before starting the service.', 503)
        self.client = client or httpx.Client(
            base_url=settings.openai_base_url.rstrip('/') + '/',
            headers={'Authorization': 'Bearer ' + key},
            follow_redirects=False,
        )

    def close(self):
        self.client.close()

    def _post(self, path: str, payload: dict, trace: Trace | None = None) -> dict:
        for attempt in range(2):
            remaining = trace.remaining() if trace else self.settings.provider_timeout_seconds
            timeout = min(remaining, self.settings.provider_timeout_seconds)
            try:
                response = self.client.post(path, json=payload, timeout=timeout)
            except httpx.TimeoutException as exc:
                # Avoid automatic timeout retries: the provider may already have processed/billed it.
                raise AppError('MODEL_TIMEOUT', 'The model provider timed out.', 504) from exc
            except httpx.HTTPError as exc:
                raise AppError('MODEL_UNAVAILABLE', 'Cannot reach the model provider.', 502) from exc
            if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                delay = 0.5
                if trace:
                    delay = min(delay, trace.remaining())
                    trace.add('provider', 'retry', status=response.status_code)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                code = 'MODEL_AUTH' if response.status_code in {401, 403} else 'MODEL_HTTP_ERROR'
                raise AppError(code, 'The model provider rejected the request; check configuration and quota.', 502)
            try:
                data = response.json()
            except ValueError as exc:
                raise AppError('MODEL_INVALID_OUTPUT', 'The model provider returned invalid JSON.', 502) from exc
            if not isinstance(data, dict):
                raise AppError('MODEL_INVALID_OUTPUT', 'Unexpected provider response structure.', 502)
            if trace:
                trace.remaining()
            return data
        raise AppError('MODEL_UNAVAILABLE', 'The model provider is temporarily unavailable.', 502)

    def _response(self, instructions: str, inputs: list[dict], trace: Trace, **extra) -> dict:
        data = self._post('responses', {'model': self.settings.active_llm_model,
                            'instructions': instructions, 'input': inputs,
                            'store': False, 'max_output_tokens': 3000, **extra}, trace)
        if data.get('status') != 'completed':
            raise AppError('MODEL_INCOMPLETE', 'The model did not complete a usable response.', 502)
        output = data.get('output')
        if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
            raise AppError('MODEL_INVALID_OUTPUT', 'Unexpected model output structure.', 502)
        for item in output:
            contents = item.get('content', [])
            if not isinstance(contents, list) or any(not isinstance(c, dict) for c in contents):
                raise AppError('MODEL_INVALID_OUTPUT', 'Unexpected model content structure.', 502)
            for content in contents:
                if content.get('type') == 'refusal':
                    raise AppError('MODEL_REFUSAL', 'The model declined this request.', 422)
        usage = data.get('usage', {})
        trace.add('provider', 'response', model=self.settings.active_llm_model,
                  input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'))
        return data

    @staticmethod
    def _format(model: type[BaseModel]) -> dict:
        return {'format': {'type': 'json_schema', 'name': model.__name__,
                           'strict': True, 'schema': model.model_json_schema()}}

    @staticmethod
    def _parse(data: dict, model: type[T]) -> T:
        texts = [c.get('text', '') for item in data.get('output', [])
                 for c in item.get('content', []) if c.get('type') == 'output_text']
        try:
            return model.model_validate_json(''.join(texts))
        except (ValidationError, ValueError) as exc:
            raise AppError('MODEL_INVALID_OUTPUT', 'The model output failed its schema validation.', 502) from exc

    def structured(self, instructions: str, payload: dict, model: type[T], trace: Trace) -> T:
        data = self._response(instructions,
                              [{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                              trace, text=self._format(model))
        return self._parse(data, model)

    def choose_calculator(self, instructions: str, payload: dict, argument_model: type[BaseModel],
                          trace: Trace) -> ToolTurn:
        inputs = [{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        tool = {'type': 'function', 'name': 'calculator', 'strict': True,
                'description': 'Execute bounded decimal arithmetic using supplied evidence variables.',
                'parameters': argument_model.model_json_schema()}
        data = self._response(instructions, inputs, trace, tools=[tool],
                              tool_choice={'type': 'function', 'name': 'calculator'},
                              parallel_tool_calls=False)
        calls = [x for x in data.get('output', []) if x.get('type') == 'function_call']
        if len(calls) != 1 or calls[0].get('name') != 'calculator':
            raise AppError('TOOL_PROTOCOL_ERROR', 'Exactly one calculator tool call was required.', 502)
        call = calls[0]
        try:
            args = argument_model.model_validate_json(call['arguments'])
            if not call.get('call_id'):
                raise ValueError('Missing call identifier')
        except (KeyError, ValidationError, ValueError) as exc:
            raise AppError('TOOL_PROTOCOL_ERROR', 'Invalid calculator tool arguments.', 502) from exc
        return ToolTurn(call['call_id'], call['name'], args.model_dump(),
                        inputs + data['output'], instructions)

    def complete_tool(self, turn: ToolTurn, result: dict, instructions: str,
                      model: type[T], trace: Trace) -> T:
        # Replay the complete function-call transcript because store=False is used.
        inputs = turn.transcript + [{'type': 'function_call_output',
                                    'call_id': turn.call_id, 'output': json.dumps(result)}]
        data = self._response(instructions, inputs, trace, text=self._format(model))
        return self._parse(data, model)

    def embed(self, texts: list[str], trace: Trace | None = None) -> list[list[float]]:
        if not texts:
            return []
        data = self._post('embeddings', {'model': self.settings.active_embedding_model,
                         'input': texts, 'dimensions': self.settings.embedding_dimensions,
                         'encoding_format': 'float'}, trace)
        try:
            entries = sorted(data['data'], key=lambda row: row['index'])
            if [x['index'] for x in entries] != list(range(len(texts))):
                raise ValueError('Embedding count/index mismatch')
            vectors = [x['embedding'] for x in entries]
            if any(len(x) != self.settings.embedding_dimensions for x in vectors):
                raise ValueError('Embedding dimension mismatch')
            return vectors
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError('EMBEDDING_INVALID', 'The embedding provider returned invalid vectors.', 502) from exc


class GeminiProvider(OpenAIProvider):
    """Gemini adapter: OpenAI-compatible chat completions plus native Gemini embeddings."""
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        key = settings.active_api_key.get_secret_value()
        if not key:
            raise AppError('CONFIG_MISSING', 'Set GEMINI_API_KEY before starting the service.', 503)
        self.settings = settings
        self.client = client or httpx.Client(
            base_url='https://generativelanguage.googleapis.com/v1beta/',
            headers={'Authorization': 'Bearer ' + key}, follow_redirects=False,
        )

    def _chat(self, messages: list[dict], trace: Trace, **extra) -> dict:
        data = self._post('openai/chat/completions', {
            'model': self.settings.active_llm_model, 'messages': messages,
            'max_tokens': 3000, **extra}, trace)
        try:
            choice = data['choices'][0]
            message = choice['message']
            if choice.get('finish_reason') == 'length':
                raise ValueError('truncated')
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError('MODEL_INVALID_OUTPUT', 'Unexpected Gemini response structure.', 502) from exc
        usage = data.get('usage', {})
        trace.add('provider', 'response', model=self.settings.active_llm_model,
                  input_tokens=usage.get('prompt_tokens'), output_tokens=usage.get('completion_tokens'))
        return message

    @staticmethod
    def _json_format(model: type[BaseModel]) -> dict:
        return {'type': 'json_schema', 'json_schema': {'name': model.__name__, 'strict': True,
                'schema': model.model_json_schema()}}

    def structured(self, instructions: str, payload: dict, model: type[T], trace: Trace) -> T:
        message = self._chat([
            {'role': 'system', 'content': instructions},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], trace,
            response_format=self._json_format(model))
        try:
            return model.model_validate_json(message['content'])
        except (KeyError, ValidationError, ValueError, TypeError) as exc:
            raise AppError('MODEL_INVALID_OUTPUT', 'The Gemini output failed its schema validation.', 502) from exc

    def choose_calculator(self, instructions: str, payload: dict, argument_model: type[BaseModel],
                          trace: Trace) -> ToolTurn:
        messages = [{'role': 'system', 'content': instructions},
                    {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
        tool = {'type': 'function', 'function': {'name': 'calculator',
                'description': 'Execute bounded decimal arithmetic using supplied evidence variables.',
                'parameters': argument_model.model_json_schema(), 'strict': True}}
        message = self._chat(messages, trace, tools=[tool], tool_choice='required')
        calls = message.get('tool_calls', [])
        if len(calls) != 1 or calls[0].get('function', {}).get('name') != 'calculator':
            raise AppError('TOOL_PROTOCOL_ERROR', 'Exactly one Gemini calculator tool call was required.', 502)
        call = calls[0]
        try:
            args = argument_model.model_validate_json(call['function']['arguments'])
            call_id = call['id']
            if not call_id:
                raise ValueError('Missing call identifier')
        except (KeyError, ValidationError, ValueError, TypeError) as exc:
            raise AppError('TOOL_PROTOCOL_ERROR', 'Invalid Gemini calculator arguments.', 502) from exc
        return ToolTurn(call_id, 'calculator', args.model_dump(), messages + [
            {'role': 'assistant', 'content': None, 'tool_calls': calls}], instructions)

    def complete_tool(self, turn: ToolTurn, result: dict, instructions: str,
                      model: type[T], trace: Trace) -> T:
        messages = turn.transcript + [{'role': 'tool', 'tool_call_id': turn.call_id,
                                      'content': json.dumps(result, ensure_ascii=False)}]
        messages[0] = {'role': 'system', 'content': instructions}
        message = self._chat(messages, trace, response_format=self._json_format(model))
        try:
            return model.model_validate_json(message['content'])
        except (KeyError, ValidationError, ValueError, TypeError) as exc:
            raise AppError('MODEL_INVALID_OUTPUT', 'The Gemini output failed its schema validation.', 502) from exc

    def embed(self, texts: list[str], trace: Trace | None = None) -> list[list[float]]:
        if not texts:
            return []
        vectors = []
        batch_size = 32
        model_name = f'models/{self.settings.active_embedding_model}'
        for offset in range(0, len(texts), batch_size):
            chunk = texts[offset:offset + batch_size]
            requests = [
                {
                    'model': model_name,
                    'content': {'parts': [{'text': t}]},
                    'outputDimensionality': self.settings.embedding_dimensions,
                }
                for t in chunk
            ]
            data = self._post(f'{model_name}:batchEmbedContents', {'requests': requests}, trace)
            try:
                embeddings = data.get('embeddings', [])
                if len(embeddings) != len(chunk):
                    raise ValueError('Embedding count mismatch in batchEmbedContents')
                for item in embeddings:
                    values = item['values']
                    if len(values) != self.settings.embedding_dimensions:
                        raise ValueError('Embedding dimension mismatch')
                    vectors.append(values)
            except (KeyError, TypeError, ValueError) as exc:
                raise AppError('EMBEDDING_INVALID', 'Gemini returned invalid embedding vectors.', 502) from exc
        return vectors

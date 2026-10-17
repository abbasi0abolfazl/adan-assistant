import json
import httpx
import pytest
from app.config import Settings
from app.contracts import Plan, FinalAnswer, CalculatorArguments
from app.llm import OpenAIProvider, GeminiProvider, LLMProvider
from app.errors import AppError
from app.trace import Trace
from .fakes import plan, final, ScriptedProvider


def response_json(value):
    return {'status':'completed','output':[{'type':'message','role':'assistant',
          'content':[{'type':'output_text','text':json.dumps(value)}]}],
          'usage':{'input_tokens':10,'output_tokens':5}}


def provider(handler):
    client = httpx.Client(base_url='https://test.invalid/v1/',transport=httpx.MockTransport(handler))
    return OpenAIProvider(Settings(openai_api_key='unit-test-placeholder'),client)


def test_responses_structured_contract():
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == '/v1/responses'
        assert payload['store'] is False
        assert payload['text']['format']['strict'] is True
        schema = payload['text']['format']['schema']
        assert schema['additionalProperties'] is False
        assert set(schema['required']) == set(schema['properties'])
        return httpx.Response(200,json=response_json(plan()))
    p = provider(handler)
    assert p.structured('instructions',{},Plan,Trace('x')).route == 'database'
    p.close()


def test_native_function_call_complete_protocol():
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests)==1:
            assert payload['tools'][0]['type']=='function'
            assert payload['tool_choice']=={'type':'function','name':'calculator'}
            return httpx.Response(200,json={'status':'completed','output':[
                {'type':'function_call','id':'fc_1','call_id':'call_1','name':'calculator',
                 'arguments':json.dumps({'expression':'x/100','precision':2})}]})
        assert payload['input'][-1]['type']=='function_call_output'
        assert payload['input'][-1]['call_id']=='call_1'
        assert payload['input'][-2]['type']=='function_call'
        return httpx.Response(200,json=response_json(final('1.00',sql=False,calc=True)))
    p = provider(handler)
    turn = p.choose_calculator('calculate',{},CalculatorArguments,Trace('x'))
    result = p.complete_tool(turn,{'result':'1.00'},'final',FinalAnswer,Trace('x'))
    assert result.used_calculation
    p.close()


@pytest.mark.parametrize('status', [401,403,400,404])
def test_provider_errors_do_not_leak_secrets(status):
    p = provider(lambda request: httpx.Response(status,json={'error':'secret-unredacted-provider-data'}))
    with pytest.raises(AppError) as error:
        p.structured('x',{},Plan,Trace('x'))
    assert 'secret-unredacted' not in str(error.value)
    p.close()


def test_rate_limit_retries_once(monkeypatch):
    monkeypatch.setattr('app.llm.time.sleep',lambda seconds:None)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(429,json={'error':'rate limited'})
    p=provider(handler)
    with pytest.raises(AppError):
        p.structured('x',{},Plan,Trace('x'))
    assert len(calls)==2
    p.close()


def test_timeout_not_retried():
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('private payload',request=request)
    p=provider(handler)
    with pytest.raises(AppError) as error:
        p.structured('x',{},Plan,Trace('x'))
    assert error.value.code=='MODEL_TIMEOUT' and len(calls)==1
    p.close()


def test_malformed_model_response():
    p=provider(lambda r: httpx.Response(200,json=response_json({'route':'invented'})))
    with pytest.raises(AppError) as error:
        p.structured('x',{},Plan,Trace('x'))
    assert error.value.code=='MODEL_INVALID_OUTPUT'
    p.close()


def test_refusal_and_incomplete():
    for data,code in [({'status':'incomplete','output':[]},'MODEL_INCOMPLETE'),
        ({'status':'completed','output':[{'content':[{'type':'refusal','refusal':'no'}]}]},'MODEL_REFUSAL')]:
        p=provider(lambda r: httpx.Response(200,json=data))
        with pytest.raises(AppError) as error:
            p.structured('x',{},Plan,Trace('x'))
        assert error.value.code==code
        p.close()


def test_embedding_reorders_response_indices():
    dim=1536
    p=provider(lambda r: httpx.Response(200,json={'data':[
        {'index':1,'embedding':[0.]*dim},{'index':0,'embedding':[1.]*dim}]}))
    assert p.embed(['a','b'])[0][0]==1.
    p.close()


def test_embedding_dimension_guard():
    p=provider(lambda r: httpx.Response(200,json={'data':[{'index':0,'embedding':[1,0]}]}))
    with pytest.raises(AppError):
        p.embed(['a'])
    p.close()


def test_empty_key_rejected():
    with pytest.raises(AppError) as error:
        OpenAIProvider(Settings(openai_api_key=''))
    assert error.value.code=='CONFIG_MISSING'


@pytest.mark.parametrize('output', [None, 'not-an-array', [1], [{'content':None}], [{'content':['invalid']}]] )
def test_malformed_provider_structure_is_controlled(output):
    p=provider(lambda r: httpx.Response(200,json={'status':'completed','output':output}))
    with pytest.raises(AppError) as error:
        p.structured('x',{},Plan,Trace('x'))
    assert error.value.code=='MODEL_INVALID_OUTPUT'
    p.close()


def test_llm_provider_protocol_conformance():
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    openai = OpenAIProvider(Settings(openai_api_key='placeholder'), client=httpx.Client(transport=transport))
    assert isinstance(openai, LLMProvider)
    openai.close()

    gemini = GeminiProvider(Settings(provider='gemini', gemini_api_key='placeholder'), client=httpx.Client(transport=transport))
    assert isinstance(gemini, LLMProvider)
    gemini.close()

    scripted = ScriptedProvider()
    assert isinstance(scripted, LLMProvider)


def gemini_provider(handler):
    client = httpx.Client(base_url='https://generativelanguage.googleapis.com/v1beta/',
                          transport=httpx.MockTransport(handler))
    return GeminiProvider(Settings(provider='gemini', gemini_api_key='unit-test-placeholder'), client)


def test_gemini_structured_contract():
    def handler(request):
        payload = json.loads(request.content)
        assert request.url.path == '/v1beta/openai/chat/completions'
        assert payload['messages'][0]['role'] == 'system'
        assert payload['response_format']['type'] == 'json_schema'
        return httpx.Response(200, json={
            'choices': [{
                'message': {'content': json.dumps(plan())},
                'finish_reason': 'stop'
            }],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5}
        })
    p = gemini_provider(handler)
    assert p.structured('instructions', {}, Plan, Trace('x')).route == 'database'
    p.close()


def test_gemini_calculator_tool_protocol():
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            assert payload['tools'][0]['type'] == 'function'
            assert payload['tool_choice'] == 'required'
            return httpx.Response(200, json={
                'choices': [{
                    'message': {
                        'tool_calls': [{
                            'id': 'call_gemini_1',
                            'function': {
                                'name': 'calculator',
                                'arguments': json.dumps({'expression': 'x/100', 'precision': 2})
                            }
                        }]
                    },
                    'finish_reason': 'stop'
                }]
            })
        assert payload['messages'][-1]['role'] == 'tool'
        assert payload['messages'][-1]['tool_call_id'] == 'call_gemini_1'
        return httpx.Response(200, json={
            'choices': [{
                'message': {'content': json.dumps(final('1.00', sql=False, calc=True))},
                'finish_reason': 'stop'
            }]
        })
    p = gemini_provider(handler)
    turn = p.choose_calculator('calculate', {}, CalculatorArguments, Trace('x'))
    assert turn.call_id == 'call_gemini_1'
    result = p.complete_tool(turn, {'result': '1.00'}, 'final', FinalAnswer, Trace('x'))
    assert result.used_calculation
    p.close()


def test_gemini_batch_embed():
    dim = 1536
    def handler(request):
        payload = json.loads(request.content)
        assert ':batchEmbedContents' in request.url.path
        assert len(payload['requests']) == 2
        assert payload['requests'][0]['outputDimensionality'] == dim
        return httpx.Response(200, json={
            'embeddings': [{'values': [1.0] * dim}, {'values': [2.0] * dim}]
        })
    p = gemini_provider(handler)
    assert p.embed([]) == []
    vectors = p.embed(['hello', 'world'])
    assert len(vectors) == 2
    assert vectors[0][0] == 1.0 and vectors[1][0] == 2.0
    p.close()


def test_gemini_embed_dimension_or_count_mismatch():
    dim = 1536
    # Count mismatch
    p1 = gemini_provider(lambda r: httpx.Response(200, json={'embeddings': [{'values': [1.0] * dim}]}))
    with pytest.raises(AppError) as err1:
        p1.embed(['a', 'b'])
    assert err1.value.code == 'EMBEDDING_INVALID'
    p1.close()

    # Dimension mismatch
    p2 = gemini_provider(lambda r: httpx.Response(200, json={'embeddings': [{'values': [1.0, 2.0]}]}))
    with pytest.raises(AppError) as err2:
        p2.embed(['a'])
    assert err2.value.code == 'EMBEDDING_INVALID'
    p2.close()


def test_gemini_empty_key_rejected():
    with pytest.raises(AppError) as error:
        GeminiProvider(Settings(provider='gemini', gemini_api_key=''))
    assert error.value.code == 'CONFIG_MISSING'


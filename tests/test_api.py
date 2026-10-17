import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.contracts import AskResponse
from app.errors import AppError


class StubCoordinator:
    def run(self,request,trace):
        if request.question=='controlled error':
            raise AppError('SQL_FORBIDDEN','Read-only operation denied.',422)
        if request.question=='unexpected error':
            raise RuntimeError('never expose /private/path or api-key')
        return AskResponse(request_id=trace.request_id,status='answered',answer='fixture only',
                           route='documents',sources=[],sql=[],calculations=[],trace=[],warnings=[])


@pytest.fixture
def client():
    with TestClient(create_app(StubCoordinator()),raise_server_exceptions=False) as client:
        yield client


def test_healthy_and_contract(client):
    assert client.get('/health/live').status_code==200
    assert client.get('/health/ready').json()['model_probed'] is False
    answer=client.post('/ask',json={'question':'A valid sample question'})
    assert answer.status_code==200 and answer.json()['request_id']


@pytest.mark.parametrize('payload', [{}, {'question':'x'}, {'question':'   '}, {'question':'x'*2001},
    {'question':'hello','language':'xx'}, {'question':'hello','extra':True}, {'question':3},
    {'question':'bad\u0000value'}])
def test_validation(client,payload):
    assert client.post('/ask',json=payload).status_code==422


def test_body_limit(client):
    assert client.post('/ask',content=b'X'*17000).status_code==413


def test_safe_error(client):
    result=client.post('/ask',json={'question':'controlled error'})
    assert result.status_code==422
    assert result.json()['error']['code']=='SQL_FORBIDDEN'
    assert result.json()['trace'][-1]['action']=='failed'


def test_unexpected_error_sanitized(client):
    result=client.post('/ask',json={'question':'unexpected error'})
    assert result.status_code==500
    assert 'private/path' not in result.text and 'api-key' not in result.text


def test_concurrency_bound(client):
    sem=client.app.state.inflight
    count=0
    while sem.acquire(blocking=False): count+=1
    try:
        assert client.post('/ask',json={'question':'A valid question'}).status_code==503
    finally:
        for _ in range(count): sem.release()

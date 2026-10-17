import logging
import threading
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .bootstrap import bootstrap
from .config import Settings
from .contracts import AskRequest, AskResponse
from .errors import AppError
from .trace import Trace


class BoundedBodyMiddleware:
    def __init__(self, app, limit=16384):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        scope.setdefault('state', {})['request_id'] = str(uuid.uuid4())
        messages, total = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            total += len(message.get('body', b''))
            if total > self.limit:
                reply = JSONResponse({'error': {'code': 'BODY_TOO_LARGE', 'message': 'Request body exceeds 16 KiB.'}}, status_code=413)
                return await reply(scope, receive, send)
            messages.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()
        await self.app(scope, replay, send)


def create_app(coordinator=None, settings=None):
    settings = settings or Settings()
    supplied_coordinator = coordinator

    @asynccontextmanager
    async def lifespan(app):
        provider = None
        if supplied_coordinator is None:
            app.state.coordinator, provider = bootstrap(settings)
        else:
            app.state.coordinator = supplied_coordinator
        app.state.inflight = threading.BoundedSemaphore(settings.max_inflight)
        yield
        if provider:
            provider.close()

    app = FastAPI(title='Adan - Nava Evidence Assistant', version='1.0.0', lifespan=lifespan)
    app.add_middleware(BoundedBodyMiddleware)

    @app.exception_handler(AppError)
    async def safe_error(request: Request, exc: AppError):
        trace = getattr(request.state, 'trace', None)
        return JSONResponse(status_code=exc.http_status, content={
            'request_id': request.state.request_id,
            'error': {'code': exc.code, 'message': exc.message},
            'trace': trace.events if trace else []})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger('adan').error('Unexpected error type=%s request_id=%s',
                                      type(exc).__name__, getattr(request.state, 'request_id', ''))
        return JSONResponse(status_code=500, content={
            'request_id': getattr(request.state, 'request_id', ''),
            'error': {'code': 'INTERNAL_ERROR', 'message': 'An unexpected internal error occurred.'}})

    @app.get('/health/live')
    def live():
        return {'status': 'alive'}

    @app.get('/health/ready')
    def ready():
        return {'status': 'ready', 'model_probed': False,
                'note': 'Startup initialization completed; this endpoint does not spend API credits.'}

    @app.post('/ask', response_model=AskResponse)
    def ask(body: AskRequest, request: Request):
        semaphore = app.state.inflight
        if not semaphore.acquire(blocking=False):
            raise AppError('BUSY', 'Too many concurrent requests; retry shortly.', 503)
        trace = Trace(request.state.request_id, settings.request_deadline_seconds)
        request.state.trace = trace
        try:
            return app.state.coordinator.run(body, trace)
        except AppError as exc:
            trace.add('coordinator', 'failed', error_code=exc.code)
            raise
        finally:
            semaphore.release()
    return app


logging.basicConfig(level=logging.INFO, format='%(message)s')
app = create_app()

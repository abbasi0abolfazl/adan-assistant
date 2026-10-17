import json
import logging
import time
from dataclasses import dataclass, field
from .errors import AppError

logger = logging.getLogger('adan.audit')


@dataclass
class Trace:
    request_id: str
    deadline_seconds: float = 150
    started: float = field(default_factory=time.monotonic)
    events: list[dict] = field(default_factory=list)

    def remaining(self) -> float:
        result = self.deadline_seconds - (time.monotonic() - self.started)
        if result <= 0:
            raise AppError('REQUEST_TIMEOUT', 'The request time budget was exceeded.', 504)
        return result

    def add(self, component: str, action: str, **details):
        self.events.append({'step': len(self.events) + 1, 'component': component,
                            'action': action, 'elapsed_ms': round((time.monotonic()-self.started)*1000),
                            'details': details})
        # Logs intentionally exclude questions, SQL parameters, evidence text and API keys.
        logger.info(json.dumps({'request_id': self.request_id, 'component': component,
                                'action': action, 'step': len(self.events)}))

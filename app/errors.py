class AppError(Exception):
    """A safe, public error; never expose provider bodies or filesystem paths."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status

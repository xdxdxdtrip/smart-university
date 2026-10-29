"""Доменные исключения бизнес-логики. В main.py они превращаются в HTTP-ответы."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class BookingValidationError(DomainError):
    status_code = 400


class BookingConflictError(DomainError):
    status_code = 409


class PermissionDeniedError(DomainError):
    status_code = 403


class NotFoundError(DomainError):
    status_code = 404

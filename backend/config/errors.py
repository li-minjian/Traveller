"""Uniform error body shared by every API error response.

Shape: {"error": {"code": str, "message": str, "fields"?: {field: [str, ...]}}}
"""

NOT_FOUND_MESSAGE = "The requested resource was not found."


def error_body(code: str, message: str, fields: dict | None = None) -> dict:
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}

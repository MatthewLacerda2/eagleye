"""The one non-JSON response: a JPEG frame.

A binary image cannot be a Pydantic body, so the contract for it is declared
here, beside the other schemas, as a typed file response.
"""

from fastapi.responses import FileResponse


class JpegResponse(FileResponse):
    """A stored camera frame, served as ``image/jpeg``."""

    media_type = "image/jpeg"

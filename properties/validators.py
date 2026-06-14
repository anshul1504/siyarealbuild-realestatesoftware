from django.core.exceptions import ValidationError


MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_CONTENT_TYPES = IMAGE_CONTENT_TYPES | {"application/pdf"}


def validate_uploaded_file(upload, *, allowed_content_types, max_size, label):
    if not upload or not hasattr(upload, "size"):
        return upload
    if upload.size > max_size:
        raise ValidationError(f"{label} size must be {max_size // (1024 * 1024)} MB or less.")
    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in allowed_content_types:
        raise ValidationError(f"Upload a supported {label.lower()} file only.")
    return upload


def validate_property_image(upload):
    return validate_uploaded_file(upload, allowed_content_types=IMAGE_CONTENT_TYPES, max_size=MAX_IMAGE_SIZE, label="Image")


def validate_property_document(upload):
    return validate_uploaded_file(upload, allowed_content_types=DOCUMENT_CONTENT_TYPES, max_size=MAX_DOCUMENT_SIZE, label="Document")

import uuid

from dotenv import load_dotenv

from app.repositories.storage_client import (
    get_storage_bucket,
)


load_dotenv()


def main() -> None:
    bucket = get_storage_bucket()

    if not bucket.exists():
        raise RuntimeError(
            f"Bucket does not exist: {bucket.name}"
        )

    object_name = (
        "_connection_tests/"
        f"{uuid.uuid4()}.txt"
    )

    blob = bucket.blob(object_name)

    blob.upload_from_string(
        "Cloud Storage connection successful",
        content_type="text/plain",
    )

    print("Cloud Storage connection successful")
    print("Bucket:", bucket.name)
    print("Object:", object_name)


if __name__ == "__main__":
    main()
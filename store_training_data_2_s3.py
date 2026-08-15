from pathlib import Path
from dotenv import load_dotenv
from os import environ
import logging
import boto3

load_dotenv(dotenv_path=Path(__file__).parent / "local.env")

logging.basicConfig(format="%(asctime)s:%(name)s:%(levelname)s - %(message)s", level=logging.INFO)

# S3 key matches the artifact URL ai://default/app/data registered in ai_core_prep.py.
# The object store secret has no pathPrefix, so the key is used as-is.
S3_KEY = "app/data/inspections.csv"
LOCAL_FILE = Path(__file__).parent / "data" / "inspections.csv"


def upload():
    s3 = boto3.client(
        "s3",
        region_name=environ["S3_REGION"],
        endpoint_url=f"https://{environ['S3_HOST']}",
        aws_access_key_id=environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=environ["S3_SECRET_ACCESS_KEY"],
    )

    bucket = environ["S3_BUCKET"]
    logging.info(f"Uploading {LOCAL_FILE} → s3://{bucket}/{S3_KEY}")
    s3.upload_file(str(LOCAL_FILE), bucket, S3_KEY)
    logging.info("Upload complete.")


if __name__ == "__main__":
    upload()

from pathlib import Path
from dotenv import load_dotenv
from os import environ
import base64
import json
import logging
import time
import yaml

from ai_api_client_sdk.ai_api_v2_client import AIAPIV2Client
from ai_api_client_sdk.models.artifact import Artifact
from ai_api_client_sdk.models.input_artifact_binding import InputArtifactBinding
from ai_api_client_sdk.models.status import Status

load_dotenv(dotenv_path=Path(__file__).parents[1] / "local.env")

# Required in local.env but not yet present — add these two lines:
#   GITHUB_USER=<your-github-username>
#   GITHUB_TOKEN=<your-github-personal-access-token>

logging.basicConfig(format="%(asctime)s:%(name)s:%(levelname)s - %(message)s", level=logging.INFO)

RESOURCE_GROUP = environ["AICORE_RESOURCE_GROUP"]
CONNECTION_NAME = "default"
PATH_PREFIX = "app"

_ROOT = Path(__file__).parents[1]
TRAINING_WORKFLOW = _ROOT / "workflows" / "train.yaml"
SERVING_WORKFLOW = _ROOT / "workflows" / "serve.yaml"


def _admin_client():
    return AIAPIV2Client(
        base_url=environ["BTP_AI_API_URL"] + "/v2",
        auth_url=environ["BTP_TOKEN_URL"],
        client_id=environ["BTP_CLIENT_ID"],
        client_secret=environ["BTP_CLIENT_SECRET"],
    )


def _lm_client():
    return AIAPIV2Client(
        base_url=environ["BTP_AI_API_URL"] + "/v2/lm",
        auth_url=environ["BTP_TOKEN_URL"],
        client_id=environ["BTP_CLIENT_ID"],
        client_secret=environ["BTP_CLIENT_SECRET"],
        resource_group=RESOURCE_GROUP,
    )


def _try(label, fn):
    try:
        fn()
        logging.info(f"{label}: done")
    except Exception as e:
        logging.warning(f"{label}: skipped ({e})")


def register_git_repository(client):
    def _call():
        client.rest_client.post(
            path="/admin/repositories",
            body={
                "name": "restaurant-inspections-repo",
                "url": environ["GITHUB_REPO"],
                "username": environ["GITHUB_USER"],
                "password": environ["GITHUB_TOKEN"],
            },
        )
    _try("Register Git repository", _call)


def register_application(client):
    def _call():
        client.rest_client.post(
            path="/admin/applications",
            body={
                "applicationName": environ["AICORE_APP_NAME"],
                "repositoryUrl": environ["GITHUB_REPO"],
                "revision": "HEAD",
                "path": "workflows",
            },
        )
    _try("Register application", _call)


def register_docker_secret(client):
    docker_config = {
        "auths": {
            "https://index.docker.io/v1/": {
                "username": environ["DOCKER_HUB_USER"],
                "password": environ["DOCKER_HUB_TOKEN"],
                "email": environ["DOCKER_HUB_EMAIL"],
                "auth": base64.b64encode(
                    f"{environ['DOCKER_HUB_USER']}:{environ['DOCKER_HUB_TOKEN']}".encode()
                ).decode(),
            }
        }
    }
    def _call():
        client.rest_client.post(
            path="/admin/dockerRegistrySecrets",
            body={
                "name": "docker-registry-secret",
                "data": {
                    ".dockerconfigjson": base64.b64encode(
                        json.dumps(docker_config).encode()
                    ).decode()
                },
            },
        )
    _try("Register Docker registry secret", _call)


def create_resource_group(client):
    def _call():
        client.rest_client.post(
            path="/admin/resourceGroups",
            body={"resourceGroupId": RESOURCE_GROUP},
        )
    _try(f"Create resource group '{RESOURCE_GROUP}'", _call)


def register_s3_secret(client):
    def _call():
        client.rest_client.post(
            path="/admin/objectStoreSecrets",
            body={
                "name": CONNECTION_NAME,
                "type": "S3",
                "endpoint": environ["S3_HOST"],
                "bucket": environ["S3_BUCKET"],
                "pathPrefix": PATH_PREFIX,
                "region": environ["S3_REGION"],
                "data": {
                    "AWS_ACCESS_KEY_ID": environ["S3_ACCESS_KEY_ID"],
                    "AWS_SECRET_ACCESS_KEY": environ["S3_SECRET_ACCESS_KEY"],
                },
            },
            resource_group=RESOURCE_GROUP,
        )
    _try("Register S3 object store secret", _call)


def register_training_artifact(lm_client):
    logging.info("Registering training dataset artifact...")
    with open(TRAINING_WORKFLOW) as f:
        workflow = yaml.safe_load(f)
    scenario_id = workflow["metadata"]["labels"]["scenarios.ai.sap.com/id"]

    resp = lm_client.artifact.create(
        name=RESOURCE_GROUP,
        kind=Artifact.Kind.DATASET,
        url=f"ai://{CONNECTION_NAME}/data",
        description="Restaurant inspections dataset",
        scenario_id=scenario_id,
    )
    logging.info(f"Artifact registered: {resp.id}")
    return resp.id, scenario_id, workflow


def create_training_configuration(lm_client, artifact_id, scenario_id, workflow):
    logging.info("Creating training configuration...")
    input_artifact_name = workflow["spec"]["templates"][0]["inputs"]["artifacts"][0]["name"]
    executable_id = workflow["metadata"]["name"]

    resp = lm_client.configuration.create(
        name=RESOURCE_GROUP,
        scenario_id=scenario_id,
        executable_id=executable_id,
        parameter_bindings=[],
        input_artifact_bindings=[
            InputArtifactBinding(key=input_artifact_name, artifact_id=artifact_id)
        ],
    )
    logging.info(f"Training configuration created: {resp.id}")
    return resp.id


def run_training(lm_client, config_id):
    logging.info("Starting training execution...")
    execution_resp = lm_client.execution.create(config_id)
    logging.info(f"Execution started: {execution_resp.id}")

    status = None
    while status not in (Status.COMPLETED, Status.DEAD):
        time.sleep(10)
        execution = lm_client.execution.get(execution_resp.id)
        status = execution.status
        logging.info(f"Training status: {status}")

    if status == Status.DEAD:
        raise RuntimeError(f"Training execution {execution_resp.id} failed")

    model_artifact_id = execution.output_artifacts[0].id
    logging.info(f"Training complete. Model artifact: {model_artifact_id}")
    return model_artifact_id


def create_serving_configuration(lm_client, model_artifact_id):
    logging.info("Creating serving configuration...")
    with open(SERVING_WORKFLOW) as f:
        workflow = yaml.safe_load(f)

    scenario_id = workflow["metadata"]["labels"]["scenarios.ai.sap.com/id"]
    input_artifact_name = workflow["spec"]["inputs"]["artifacts"][0]["name"]
    executable_id = workflow["metadata"]["name"]

    resp = lm_client.configuration.create(
        name=f"{RESOURCE_GROUP}-serve",
        scenario_id=scenario_id,
        executable_id=executable_id,
        parameter_bindings=[],
        input_artifact_bindings=[
            InputArtifactBinding(key=input_artifact_name, artifact_id=model_artifact_id)
        ],
    )
    logging.info(f"Serving configuration created: {resp.id}")
    return resp.id


def deploy_model(lm_client, serve_config_id):
    logging.info("Creating deployment...")
    deployment_resp = lm_client.deployment.create(serve_config_id)
    logging.info(f"Deployment started: {deployment_resp.id}")

    status = None
    while status not in (Status.RUNNING, Status.DEAD):
        time.sleep(10)
        deployment = lm_client.deployment.get(deployment_resp.id)
        status = deployment.status
        logging.info(f"Deployment status: {status}")

    if status == Status.DEAD:
        raise RuntimeError(f"Deployment {deployment_resp.id} failed")

    logging.info(f"Deployment running at: {deployment.deployment_url}")
    return deployment.deployment_url


def main():
    admin = _admin_client()
    lm = _lm_client()

    register_git_repository(admin)
    register_application(admin)
    register_docker_secret(admin)
    create_resource_group(admin)
    register_s3_secret(admin)

    artifact_id, scenario_id, workflow = register_training_artifact(lm)
    config_id = create_training_configuration(lm, artifact_id, scenario_id, workflow)
    model_artifact_id = run_training(lm, config_id)

    serve_config_id = create_serving_configuration(lm, model_artifact_id)
    deployment_url = deploy_model(lm, serve_config_id)

    logging.info(f"Done. Inference endpoint: {deployment_url}/v1/models/{RESOURCE_GROUP}:predict")


if __name__ == "__main__":
    main()

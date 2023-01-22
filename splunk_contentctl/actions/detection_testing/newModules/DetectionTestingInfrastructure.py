import threading
from pydantic import BaseModel
import abc
import requests
import splunklib.client as client

from splunk_contentctl.objects.test_config import TestConfig


class DetectionTestingInfrastructure(BaseModel, abc.ABC):
    # thread: threading.Thread = threading.Thread()
    config: TestConfig

    class Config:
        arbitrary_types_allowed = True

    # def __init__(self):
    #    pass

    def setup(self):
        pass

    def connect_to_api(self) -> client.Service:

        test_instance_api_port = 8089
        conn = client.connect(
            host=self.config.test_instance_address,
            port=test_instance_api_port,
            username=self.config.splunk_app_username,
            password=self.config.splunk_app_password,
        )
        return conn

    def configure_imported_roles(
        self, imported_roles: list[str] = ["user", "power", "can_delete"]
    ):
        c = self.connect_to_api()
        c.roles.post(self.config.splunk_app_username, imported_roles=imported_roles)

    def configure_delete_indexes(self, indexes: list[str] = ["_*", "*", "main"]):
        test_instance_api_port = 8089
        endpoint = "services/properties/authorize/default/deleteIndexesAllowed"
        indexes_encoded = ";".join(indexes)

        target = f"https://{self.config.test_instance_address}:{test_instance_api_port}/{endpoint}"
        # is there a way to do this with the Python API? Probably...
        res = requests.post(
            target,
            data={"value": indexes_encoded},
            verify=False,
            auth=(self.config.splunk_app_username, self.config.splunk_app_password),
        )
        res.raise_for_status()

    def configure_conf_file_datamodels(self):
        pass

    def execute(self):
        pass

    def status(self):
        pass

    def check_health(self):
        pass

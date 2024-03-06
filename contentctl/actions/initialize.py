
import shutil
import os
import pathlib

from pydantic import RootModel 
from contentctl.objects.config import init, test
from contentctl.output.yml_writer import YmlWriter


class Initialize:

    def execute(self, input_dto: init) -> None:
        #construct a test object from the init object        
        full_test_object:test = test.model_validate(input_dto.model_dump())
         
        YmlWriter.writeYmlFile(os.path.join(input_dto.path, 'contentctl.yml'), RootModel[init](test).model_dump())

        

        #Create the following empty directories:
        for emptyDir in ['lookups', 'baselines', 'docs', 'reporting', 'investigations']:
            #Throw an error if this directory already exists
            (input_dto.path/emptyDir).mkdir(exist_ok=False)
        

        #copy the contents of all template directories
        for templateDir, targetDir in [
            ('../templates/app_template', 'app_template'),
            ('../templates/deployments/', 'deployments'),
            ('../templates/detections/', 'detections'),
            ('../templates/macros/','macros'),
            ('../templates/stories/', 'stories'),
        ]:
            source_directory = pathlib.Path(os.path.dirname(__file__))/templateDir
            target_directory = input_dto.path/targetDir
            #Throw an exception if the target exists
            shutil.copytree(source_directory, targetDir, dirs_exist_ok=False)
        
        #Create the config file as well
        shutil.copyfile(pathlib.Path(os.path.dirname(__file__))/'../templates/README','README')


        print(f"The app '{input_dto.app.title}' has been initialized. "
              "Please run 'contentctl new --type {detection,story}' to create new content")


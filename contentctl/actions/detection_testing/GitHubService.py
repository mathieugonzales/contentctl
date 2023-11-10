import csv
import glob
import logging
import os
import pathlib
import subprocess
import sys
from typing import Union, Tuple
from docker import types
import datetime
import git
import yaml
from git.objects import base

from contentctl.objects.detection import Detection
from contentctl.objects.story import Story
from contentctl.objects.baseline import Baseline
from contentctl.objects.investigation import Investigation
from contentctl.objects.playbook import Playbook
from contentctl.objects.macro import Macro
from contentctl.objects.lookup import Lookup
from contentctl.objects.unit_test import UnitTest

from contentctl.objects.enums import DetectionTestingMode, DetectionStatus, AnalyticsType
import random
import pathlib
from contentctl.helper.utils import Utils

from contentctl.objects.test_config import TestConfig
from contentctl.actions.generate import DirectorOutputDto

# Logger
logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)


SSA_PREFIX = "ssa___"


class GithubService:
    def get_all_content(self, director: DirectorOutputDto) -> DirectorOutputDto:
        # get a new director that will be used for testing.
        return DirectorOutputDto(
            self.get_detections(director),
            self.get_stories(director),
            self.get_baselines(director),
            self.get_investigations(director),
            self.get_playbooks(director),
            self.get_macros(director),
            self.get_lookups(director),
            [],
            []
        )

    def get_stories(self, director: DirectorOutputDto) -> list[Story]:
        stories: list[Story] = []
        return stories

    def get_baselines(self, director: DirectorOutputDto) -> list[Baseline]:
        baselines: list[Baseline] = []
        return baselines

    def get_investigations(self, director: DirectorOutputDto) -> list[Investigation]:
        investigations: list[Investigation] = []
        return investigations

    def get_playbooks(self, director: DirectorOutputDto) -> list[Playbook]:
        playbooks: list[Playbook] = []
        return playbooks

    def get_macros(self, director: DirectorOutputDto) -> list[Macro]:
        macros: list[Macro] = []
        return macros

    def get_lookups(self, director: DirectorOutputDto) -> list[Lookup]:
        lookups: list[Lookup] = []
        return lookups

    def filter_detections_by_status(self, detections: list[Detection], status_to_test: set[AnalyticsType])->list[Detection]:
        return detections

    def filter_detections_by_type(self, detections: list[Detection])->list[Detection]:
        return detections

    def get_detections(self, director: DirectorOutputDto) -> list[Detection]:
        if self.config.mode == DetectionTestingMode.selected:
            detections =  self.get_detections_selected(director)
        elif self.config.mode == DetectionTestingMode.all:
            detections =  self.get_detections_all(director)
        elif self.config.mode == DetectionTestingMode.changes:
            detections =  self.get_detections_changed(director)
        else:
            raise (
                Exception(
                    f"Error: Unsupported detection testing mode in GithubServer: {self.config.mode}"
                )
            )
        
        detections = self.filter_detections_by_status(detections)
        detections = self.filter_detections_by_type(detections)
        return detections

    def get_detections_selected(self, director: DirectorOutputDto) -> list[Detection]:
        detections_to_test: list[Detection] = []
        requested_set = set(self.requested_detections)
        missing_detections: set[pathlib.Path] = set()

        for requested in requested_set:
            matching = list(
                filter(
                    lambda detection: pathlib.Path(detection.file_path).resolve()
                    == requested.resolve(),
                    director.detections,
                )
            )
            if len(matching) == 1:
                detections_to_test.append(matching.pop())
            elif len(matching) == 0:
                missing_detections.add(requested)
            else:
                raise (
                    Exception(
                        f"Error: multiple detection files found when attemping to resolve [{str(requested)}]"
                    )
                )

        if len(missing_detections) > 0:
            missing_detections_str = "\n\t - ".join(
                [str(path.absolute()) for path in missing_detections]
            )
            print(director.detections)
            raise (
                Exception(
                    f"Failed to find the following detection file(s) for testing:\n\t - {missing_detections_str}"
                )
            )

        return detections_to_test

    def get_detections_all(self, director: DirectorOutputDto) -> list[Detection]:
        # Assume we don't need to remove anything, like deprecated or experimental from this
        return director.detections

    def get_detections_changed(self, director: DirectorOutputDto) -> list[Detection]:
        if self.repo is None:
            raise (
                Exception(
                    f"Error: self.repo must be initialized before getting changed detections."
                )
            )
        
        target_branch_repo_object = self.repo.commit(f"origin/{self.config.version_control_config.target_branch}")
        test_branch_repo_object = self.repo.commit(self.config.version_control_config.test_branch)
        differences = target_branch_repo_object.diff(test_branch_repo_object)
        
        new_content = []
        modified_content =  []
        deleted_content = []
        renamed_content = []

        for content in differences.iter_change_type("M"):
            modified_content.append(content.b_path)
        for content in differences.iter_change_type("A"):
            new_content.append(content.b_path)
        for content in differences.iter_change_type("D"):
            deleted_content.append(content.b_path)
        for content in differences.iter_change_type("R"):
            renamed_content.append(content.b_path)
            
        #Changes to detections, macros, and lookups should trigger a re-test for anything which uses them
        changed_lookups_list = list(filter(lambda x: x.startswith("lookups"), new_content+modified_content))
        changed_lookups = set()
        
        #We must account for changes to the lookup yml AND for the underlying csv
        for lookup in changed_lookups_list:
            if lookup.endswith(".csv"): 
                lookup = lookup.replace(".csv", ".yml")
            changed_lookups.add(lookup)

        # At some point we should account for macros which contain other macros...
        changed_macros = set(filter(lambda x: x.startswith("macros"), new_content+modified_content))
        changed_macros_and_lookups = set([str(pathlib.Path(filename).absolute()) for filename in changed_lookups.union(changed_macros)])

        changed_detections = set(filter(lambda x: x.startswith("detections"), new_content+modified_content+renamed_content))

        #Check and see if content that has been modified uses any of the changed macros or lookups
        for detection in director.detections:
            deps = set([content.file_path for content in detection.get_content_dependencies()])
            if not deps.isdisjoint(changed_macros_and_lookups):
                changed_detections.add(detection.file_path)

        changed_detections_string = '\n - '.join(changed_detections)
        print(f"The following [{len(changed_detections)}] detections, or their dependencies (macros/lookups), have changed:\n - {changed_detections_string}")
        return Detection.get_detections_from_filenames(changed_detections, director.detections)

    def __init__(self, config: TestConfig):
        
        self.requested_detections: list[pathlib.Path] = []
        self.config = config
        if config.version_control_config is not None:
            self.repo = git.Repo(config.version_control_config.repo_path)
        else:
            self.repo = None
            
        
        if config.mode == DetectionTestingMode.changes: 
            if self.repo is None:
                raise Exception("You are using detection mode 'changes', but the app does not have a version_control_config in contentctl_test.yml.")
            return
        elif config.mode == DetectionTestingMode.all:
            return
        elif config.mode == DetectionTestingMode.selected:
            if config.detections_list is None or len(config.detections_list) < 1:
                raise (
                    Exception(
                        f"Error: detection mode [{config.mode}] REQUIRES that [{config.detections_list}] contains 1 or more detections, but the value is [{config.detections_list}]"
                    )
                )
            else:
                # Ensure that all of the detections exist
                missing_files = [
                    detection
                    for detection in config.detections_list
                    if not pathlib.Path(detection).is_file()
                ]
                if len(missing_files) > 0:
                    missing_string = "\n\t - ".join(missing_files)
                    raise (
                        Exception(
                            f"Error: The following detection(s) test do not exist:\n\t - {missing_files}"
                        )
                    )
                else:
                    self.requested_detections = [
                        pathlib.Path(detection_file_name)
                        for detection_file_name in config.detections_list
                    ]
                    
        else:
            raise Exception(f"Unsupported detection testing mode [{config.mode}].  "\
                            "Supported detection testing modes are [{DetectionTestingMode._member_names_}]")
        return
            

    def clone_project(self, url, project, branch):
        LOGGER.info(f"Clone Security Content Project")
        repo_obj = git.Repo.clone_from(url, project, branch=branch)
        return repo_obj


    def get_all_modified_content(
        self,
        detections: list[Detection],
        paths: list[pathlib.Path] = [
            pathlib.Path("detections/"),
            pathlib.Path("tests/"),
        ],
    ) -> Tuple[list[Detection], list[Detection]]:
        # Note that at present, we only search in the 'detections' and 'tests' folders.  In the future, we could search in all
        # folders, for example to evaluate any content affected by a macro or playbook change.

        try:

            # Because we have not passed -all as a kwarg, we will have a MAX of one commit returned:
            # https://gitpython.readthedocs.io/en/stable/reference.html?highlight=merge_base#git.repo.base.Repo.merge_base
            base_commits = self.repo.merge_base(
                self.config.version_control_config.target_branch, self.config.version_control_config.test_branch
            )
            if len(base_commits) == 0:
                raise (
                    Exception(
                        f"Error, main branch '{self.config.version_control_config.target_branch}' and test branch '{self.config.version_control_config.test_branch}' do not share a common ancestor"
                    )
                )
            base_commit = base_commits[0]
            if base_commit is None:
                raise (
                    Exception(
                        f"Error, main branch '{self.config.version_control_config.target_branch}' and test branch '{self.config.version_control_config.test_branch}' common ancestor commit was 'None'"
                    )
                )

            all_changes = base_commit.diff(
                self.config.version_control_config.test_branch, paths=[str(path) for path in paths]
            )

            # distill changed files down to the paths of added or modified files
            all_changes_paths = [
                os.path.join(self.config.version_control_config.repo_path, change.b_path)
                for change in all_changes
                if change.change_type in ["M", "A"]
            ]

            # untracked_files = [detection for detection in detections if detection.file_path in self.repo.untracked_files or detection.test.file_path in self.repo.untracked_files]
            # changed_files = [detection for detection in detections if detection.file_path in all_changes or detection.test.file_path in all_changes]

            # we must do this call BEFORE the list comprehension because otherwise untracked files are enumerated on each
            # iteration through the list and it is EXTREMELY slow
            repo_untracked_files = self.repo.untracked_files

            untracked_files = [
                detection
                for detection in detections
                if detection.file_path in repo_untracked_files
                or detection.test.file_path in repo_untracked_files
            ]
            changed_files = [
                detection
                for detection in detections
                if detection.file_path in all_changes_paths
                or detection.test.file_path in all_changes_paths
            ]
        except Exception as e:
            print(f"Error enumerating modified content: {str(e)}")
            sys.exit(1)

        return untracked_files, changed_files

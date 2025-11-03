#!/usr/bin/env python3
import fnmatch
import json
import os
import shlex
import subprocess
import sys

from dataclasses import dataclass
from functools import cached_property, total_ordering
from typing import Any


DEFAULT_ENV = {
    "CI": "true",
}


@dataclass
class Artifact:
    name: str
    pattern: str


@total_ordering
class Job:
    def __init__(self, job: dict[str, Any]):
        self.job = job

    @cached_property
    def runs_on(self) -> str | None:
        match self.job.get("capabilities", []):
            case ["darwin", *_, "aarch64"]:
                return "macos-latest"
            case ["linux", *_, "aarch64"]:
                return "ubuntu-24.04-arm"
            case ["linux", *_, "amd64"]:
                return "ubuntu-latest"
            case ["windows", *_, "amd64"]:
                return "windows-latest"

    @cached_property
    def name(self) -> str:
        return self.job["name"]

    @cached_property
    def targets(self) -> list[str]:
        return self.job.get("targets", [])

    @cached_property
    def env(self) -> dict[str, str]:
        return self.job.get("environment", {}) | DEFAULT_ENV

    @cached_property
    def mx_version(self) -> str:
        for k, v in self.job.get("packages", {}).items():
            if k == "mx":
                return v.strip("=<>~")
        return "master"

    @cached_property
    def python_version(self) -> str:
        python_version = "3.12"
        for k, v in self.job.get("packages", {}).items():
            if k == "python3":
                python_version = v.strip("=<>~")
        for k, v in self.job.get("downloads", {}).items():
            if k == "PYTHON3_HOME":
                python_version = v.get("version", python_version)
        if "MX_PYTHON" in self.env:
            del self.env["MX_PYTHON"]
        if "MX_PYTHON_VERSION" in self.env:
            del self.env["MX_PYTHON_VERSION"]
        return python_version

    @cached_property
    def system_packages(self) -> list[str]:
        # TODO: support more packages
        system_packages = []
        for k, _ in self.job.get("packages", {}).items():
            if k.startswith("pip:"):
                continue
            elif k.startswith("00:") or k.startswith("01:"):
                k = k[3:]
            system_packages.append(f"'{k}'")
        return system_packages

    @cached_property
    def python_packages(self) -> list[str]:
        python_packages = []
        for k, v in self.job.get("packages", {}).items():
            if k.startswith("pip:"):
                python_packages.append(f"'{k[4:]}{v}'")
        return python_packages

    @cached_property
    def downloads(self) -> dict[str, str] | None:
        # TODO
        return None

    @staticmethod
    def common_glob(strings: list[str]) -> str:
        assert strings
        if len(strings) == 1:
            return strings[0]
        prefix = strings[0]
        for s in strings[1:]:
            i = 0
            while i < len(prefix) and i < len(s) and prefix[i] == s[i]:
                i += 1
            prefix = prefix[:i]
            if not prefix:
                break
        suffix = strings[0][len(prefix):]
        for s in strings[1:]:
            i = 1
            while i <= len(suffix) and i <= len(s) and suffix[-i] == s[-i]:
                i += 1
            if i == 1:
                suffix = ""
                break
            suffix = suffix[-(i-1):]
        return f"{prefix}*{suffix}"

    @cached_property
    def upload_artifact(self) -> Artifact | None:
        if artifacts := self.job.get("publishArtifacts", []):
            assert len(artifacts) == 1
            dir = artifacts[0].get("dir", ".")
            patterns = artifacts[0].get("patterns", ["*"])
            return Artifact(
                artifacts[0]["name"],
                "\n".join([os.path.join(dir, p) for p in patterns])
            )
        return None

    @cached_property
    def download_artifact(self) -> Artifact | None:
        if artifacts := self.job.get("requireArtifacts", []):
            pattern = self.common_glob([a["name"] for a in artifacts])
            return Artifact(pattern, artifacts[0].get("dir", "."))
        return None

    @staticmethod
    def flatten_command(args: list[str | list[str]]) -> list[str]:
        flattened_args = []
        for s in args:
            if isinstance(s, list):
                flattened_args.append(f"$( {shlex.join(s)} )")
            else:
                flattened_args.append(s)
        return flattened_args

    @cached_property
    def setup(self) -> str:
        cmds = [self.flatten_command(step) for step in self.job.get("setup", [])]
        return "\n".join(shlex.join(s) for s in cmds)

    @cached_property
    def run(self) -> str:
        cmds = [self.flatten_command(step) for step in self.job.get("run", [])]
        return "\n".join(shlex.join(s) for s in cmds)

    @cached_property
    def logs(self) -> str | None:
        logs = self.job.get("logs")
        if logs:
            return "\n".join(logs)

    def to_dict(self):
        """
        This is the interchange with the YAML file defining the Github jobs, so here
        is where we must match the strings and expectations of the Github workflow.
        """
        return {
            "name": self.name,
            "mx_version": self.mx_version,
            "os": self.runs_on,
            "python_version": self.python_version,
            "setup_steps": self.setup,
            "run_steps": self.run,
            "python_packages": " ".join(self.python_packages),
            "system_packages": " ".join(self.system_packages),
            "provide_artifact": [self.upload_artifact.name, self.upload_artifact.pattern] if self.upload_artifact else None,
            "require_artifact": [self.download_artifact.name, self.download_artifact.pattern] if self.download_artifact else None,
            "logs": self.logs,
            "env": self.env,
        }

    def __str__(self):
        return str(self.to_dict())

    def __eq__(self, other):
        if isinstance(other, Job):
            return self.to_dict() == other.to_dict()
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, Job):
            if self.job.get("runAfter") == other.name:
                return True
            if self.download_artifact and not other.download_artifact:
                return True
            if self.download_artifact and other.upload_artifact:
                if fnmatch.fnmatch(other.upload_artifact.name, self.download_artifact.name):
                    return True
                if not self.upload_artifact:
                    return True
            return False
        return NotImplemented


def get_tagged_jobs(buildspec, target):
    jobs = []
    for job in sorted([Job(build) for build in buildspec.get("builds", [])]):
        if not any(t for t in job.targets if t in [target]):
            continue
        if not "python-svm-build-gate-linux-amd64-jdk-latest" in job.name:
            continue
        if not "gate" in job.name:
            continue
        if job.runs_on not in ["ubuntu-latest"]:
            continue
        if "enterprise" in str(job):
            continue
        jobs.append(job.to_dict())
    return jobs


def main(jsonnet_bin, ci_jsonnet, target, indent=False):
    result = subprocess.check_output([jsonnet_bin, ci_jsonnet], text=True)
    buildspec = json.loads(result)
    tagged_jobs = get_tagged_jobs(buildspec, target)
    matrix = tagged_jobs
    print(json.dumps(matrix, indent=2 if indent else None))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <jsonnet_bin> <ci_jsonnet> <target>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3], indent=sys.stdout.isatty())

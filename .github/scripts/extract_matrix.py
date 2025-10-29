#!/usr/bin/env python3
import json
import shlex
import subprocess
import sys

from functools import cached_property
from typing import Any


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
        return self.job.get("environment", {})

    @cached_property
    def mx_version(self) -> str:
        for k, v in self.job.get("packages", []).items():
            if k == "mx":
                return v.strip("=<>~")
        return "master"

    @cached_property
    def python_version(self) -> str:
        python_version = "3.12"
        for k, v in self.job.get("packages", []).items():
            if k == "python3":
                python_version = v.strip("=<>~")
        for k, v in self.job.get("downloads", []).items():
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
        for k, _ in self.job.get("packages", []).items():
            if k.startswith("pip:"):
                continue
            elif k.startswith("00:") or k.startswith("01:"):
                k = k[3:]
            system_packages.append(f"'{k}'")
        return system_packages

    @cached_property
    def python_packages(self) -> list[str]:
        python_packages = []
        for k, v in self.job.get("packages", []).items():
            if k.startswith("pip:"):
                python_packages.append(f"'{k[4:]}{v}'")
        return python_packages

    @cached_property
    def downloads(self) -> dict[str, str] | None:
        # TODO
        return None

    @cached_property
    def upload_artifact(self) -> tuple[str, str] | None:
        # TODO
        return None

    @cached_property
    def download_artifact(self) -> tuple[str, str] | None:
        # TODO
        return None

    @cached_property
    def setup(self) -> str:
        return "; ".join(shlex.join(s) for s in self.job.get("setup", []))

    @cached_property
    def run(self) -> str:
        return "; ".join(shlex.join(s) for s in self.job.get("run", []))

    def to_dict(self):
        return {
            "name": self.name,
            "mx_version": self.mx_version,
            "os": self.runs_on,
            "python_version": self.python_version,
            "setup_steps": self.setup,
            "run_steps": self.run,
            "python_packages": " ".join(self.python_packages),
            "system_packages": " ".join(self.system_packages),
            "env": self.env,
        }

    def __str__(self):
        return str(self.to_dict())


def get_tagged_jobs(buildspec):
    jobs = []
    for job in buildspec.get("builds", []):
        job = Job(job)
        if not any(t for t in job.targets if t in ["tier1", "tier2", "tier3"]):
            continue
        if not "gate" in job.name:
            continue
        if job.runs_on not in ["ubuntu-latest"]:
            continue
        if "python-unittest-gate-linux" not in job.name:
            continue
        if "graal-enterprise" in str(job):
            continue
        jobs.append(job.to_dict())
    return jobs


def main(jsonnet_bin, ci_jsonnet):
    result = subprocess.check_output([jsonnet_bin, ci_jsonnet], text=True)
    buildspec = json.loads(result)
    tagged_jobs = get_tagged_jobs(buildspec)
    matrix = tagged_jobs
    print(json.dumps(matrix, indent=2 if sys.stdout.isatty() else None))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <jsonnet_bin> <ci_jsonnet>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

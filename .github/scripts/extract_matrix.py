#!/usr/bin/env python3
import json
import shlex
import subprocess
import sys


def get_tagged_jobs(buildspec):
    jobs = []
    for job in buildspec.get("builds", []):
        if not any(t for t in job.get("targets", []) if t in ["tier1", "tier2", "tier3"]):
            continue

        if not "gate" in job.get("name"):
            continue

        match job.get("capabilities", []):
            case ["darwin", *_, "aarch64"]:
                runs_on = "macos-latest"
            case ["linux", *_, "aarch64"]:
                runs_on = "ubuntu-24.04-arm"
            case ["linux", *_, "amd64"]:
                runs_on = "ubuntu-latest"
            case ["windows", *_, "amd64"]:
                runs_on = "windows-latest"
            case _:
                continue

        env = job.get("environment", {})
        mx_version = "master"
        python_version = "3.10"
        python_packages = []
        system_packages = []

        for k, v in job.get("packages", []).items():
            if k == "python3":
                python_version = v.strip("=<>~")
            elif k == "mx":
                mx_version = v.strip("=<>~")
            elif k.startswith("pip:"):
                python_packages.append(f'{k[len("pip:"):]}{v}')
            elif k.startswith("00:") or k.startswith("01:"):
                system_packages.append(f'{k[len("00:"):]}{v}')
            else:
                system_packages.append(f'{k}{v}')
            # TODO: support more cases

        for k, v in job.get("downloads", []).items():
            if k == "PYTHON3_HOME":
                python_version = v.get("version", python_version)
                if "MX_PYTHON" in env:
                    del env["MX_PYTHON"]
                if "MX_PYTHON_VERSION" in env:
                    del env["MX_PYTHON_VERSION"]
            # TODO: support more things

        job = {
            "name": job.get("name"),
            "mx_version": mx_version,
            "python_version": python_version,
            "os": runs_on,
            "setup_steps": "; ".join(shlex.join(s) for s in job.get("setup", [])),
            "run_steps": "; ".join(shlex.join(s) for s in job.get("run", [])),
            "python_packages": " ".join(python_packages),
            "system_packages": " ".join(system_packages),
            "env": env,
        }

        # Last chance to bail out
        if "graal-enterprise" in repr(job):
            continue

        jobs.append(job)

    return jobs


def main(jsonnet_bin, ci_jsonnet):
    result = subprocess.check_output([jsonnet_bin, ci_jsonnet], text=True)
    buildspec = json.loads(result)
    tagged_jobs = get_tagged_jobs(buildspec)
    matrix = {"include": tagged_jobs}
    print(json.dumps(matrix, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <jsonnet_bin> <ci_jsonnet>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

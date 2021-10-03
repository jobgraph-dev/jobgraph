from setuptools import setup, find_packages

with open("requirements/base.in", "r") as fp:
    requirements = fp.read().splitlines()

setup(
    name="gitlabci-jobraph",
    version="1.0.0",
    description="Build Gitlab CI jobgraph",
    url="TODO",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
    classifiers=(
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ),
    entry_points={"console_scripts": ["jobgraph = jobgraph.main:main"]},
    package_data={
        "jobgraph": [
            "run-task/run-task",
            "run-task/fetch-content",
            "run-task/hgrc",
            "run-task/robustcheckout.py",
        ],
        "jobgraph.test": ["automationrelevance.json"],
    },
)

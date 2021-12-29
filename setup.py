import os

from setuptools import find_packages, setup

root_dir = os.path.dirname(os.path.realpath(__file__))


with open(os.path.join(root_dir, "requirements", "base.in")) as fp:
    requirements = fp.read().splitlines()


with open(os.path.join(root_dir, "python-version.txt")) as fp:
    python_version = fp.read().strip()

with open(os.path.join(root_dir, "README.md")) as fp:
    long_description = fp.read()


setup(
    name="gitlabci-jobgraph",
    version="1.0.0",
    description="Build Gitlab CI jobgraph",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="TODO",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=requirements,
    classifiers=[
        f"Programming Language :: Python :: {python_version}",
    ],
    entry_points={"console_scripts": ["jobgraph = jobgraph.main:main"]},
)

"""Setup script for planner package."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="planner",
    version="0.1.0",
    author="Pedro Lima",
    description="A simple task planner library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pedroliman/planner",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)

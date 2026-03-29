from setuptools import setup, find_packages
from pathlib import Path

long_description = (Path(__file__).parent / "README.md").read_text(encoding="utf-8")

setup(
    name="bytecraft",
    version="0.6.2",
    description="A lightweight DSL for scaffolding files and folders",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Sourasish Das",
    license="SOCL-1.0",
    python_requires=">=3.10",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "bytecraft=bytecraft.__main__:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Build Tools",
        "Topic :: Utilities",
    ],
)

#!/usr/bin/env python3
from setuptools import setup, find_packages

description = "Control for Vis-X: Visible Integral field Spectrograph - Extreme for MagAO-X"

setup(
    name="visx",
    version="0.0.1.dev",
    url="https://github.com/magao-x/visx",
    description=description,
    author="Sebastiaan Y. Haffert",
    author_email="syhaffert@arizona.edu",
    packages=["visx"],
    # package_data={
    #     "visx": ["default.xml"],
    # },
    install_requires=[
        "purepyindi2>=0.0.0",
    ],
    entry_points={
        "console_scripts": [
            "visxCtrl=visx.xapp:main",
        ],
    },
)

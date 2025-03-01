from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="arizona-forum-api-extended",
    version="1.0",
    author="fakelag28",
    author_email="fakelag712@gmail.com",
    description="API для работы с форумом Arizona RP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/fakelag28/Arizona-Forum-API",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    install_requires=[
        "requests",
        "beautifulsoup4",
        "lxml",
    ],
) 
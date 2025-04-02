from setuptools import setup, find_packages

setup(
    name="macmcp",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastmcp",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=4.1.0",
        ],
    },
    python_requires=">=3.8",
)

from setuptools import find_namespace_packages, setup


setup(
    name="cli-anything-douyin-web",
    version="0.1.1",
    description="CLI-Anything style harness for controlling Douyin web.",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    include_package_data=True,
    install_requires=[
        "click>=8.1",
        "playwright>=1.43",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-douyin-web=cli_anything.douyin_web.douyin_web_cli:main",
            "douyin-web=cli_anything.douyin_web.douyin_web_cli:main",
        ],
    },
    python_requires=">=3.9",
)

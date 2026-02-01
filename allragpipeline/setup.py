from setuptools import setup, find_packages

setup(
    name="allragpipeline",
    version="0.1",
    # This configuration allows importing 'allragpipeline' as a top-level package
    # even though setup.py is inside the folder.
    packages=['allragpipeline'] + ['allragpipeline.' + p for p in find_packages()],
    package_dir={'allragpipeline': '.'},
)

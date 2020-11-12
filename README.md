Bamboo Migration Tools
======================

Python scripts to pull usage data from Bamboo's REST API and for migrating build plans from
Bamboo to Travis.

Requirements
------------

Python 3.5+ with Pip

Installation
------------

The scripts provided can be run in-place, just install dependencies via `pip`:

    pip install -r requirments.txt

Usage
-----

Use `bamboo-to-travis.py` to generate a `.travis.yml` equivalent for a Bamboo build plan.

Note: this does not call the Bamboo API, instead it works off a local YAML file with the Bamboo
build configation inside. Such files can be generated from Bamboo via the REST API but access
to the Bamboo server is then required in order to pull the YAML file(s) down manually, which you
must do before running the script.

To echo the `.travis.yml` file content to the console for checking, run the script with the name
of the Bamboo YAML file, e.g.

    python3 bamboo-to-travis.py DEV-PLAN1.yaml

The script is also capable of pushing the generated file to a Github repository, optionally
providing the ID of a JIRA ID to reference in the commit body. The file is pushed to a new branch
named `dev-travis-migration`, which itself is branched off `master`, and a draft pull request is
opened using this new branch.

    python3 bamboo-to-travis.py DEV-PLAN1.yaml MyGithubOrg/repo1 JIRA-11

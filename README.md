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

For best results it is recommended to install the dependencies into a dedicated virtual
environment using `venv`:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirments.txt

Usage
-----

### Dump plan and branch information

Use `plans.py`, `branches.py` and `results.py` to run through all plans, all branches of plans and
all build runs, respectively, and to dump information on them in CSV format to `stdout`, e.g.

    python3 plans.py > all_plans.csv
    python branches.py > all_branches.csv
    python results.py > all_results.csv

A new row is added in the CSV output for each plan or branch found.

### Dump build configuration

Use `export-plans.py` to run through all build plans on the Bamboo server and dump them to disk.
Note that the resulting YAML files are dumped onto the *server* filesystem, and you will need to
manually retrieve them yourself to use in the next step.

    python3 export-plans.py

In order to run this script, you should the credentials of an Bamboo admin user.

### Export to Travis

Use `bamboo-to-travis.py` to generate a `.travis.yml` equivalent for a Bamboo build plan.

Notes:

* this does not call the Bamboo API, instead it works off a local YAML file with the Bamboo
  build configation inside. Such files can be generated from Bamboo via the REST API but access
  to the Bamboo server is then required in order to pull the YAML file(s) down manually, which you
  must do before running the script.
* linked repositories defined at the global level in Bamboo do not have their details dumped in
  the Bamboo YAML file, so if the plan uses linked repositories then you must have a mapping of
  `[repository name], [repository URL]` in the file `repositories.csv` in the same directory
  where you run the script, for all linked repositories referenced

To echo the `.travis.yml` file content to the console for checking, run the script with the name
of the Bamboo YAML file, e.g.

    python3 bamboo-to-travis.py DEV-PLAN1.yaml

The script is also capable of pushing the generated file to a Github repository, optionally
providing a commit title, body. The file is pushed to a new branch named `dev-travis-migration` or
whatever custom branch name specified via `--branch`, which itself is branched off `master` by
default or any other branch specified using `--base-branch`.

    python3 bamboo-to-travis.py --base-branch=master --commit-title='New Travis build' --commit-body='Refs JIRA-11' DEV-PLAN1.yaml MyGithubOrg/repo1

If the file `.travis.yml` already exists on the branch, you can update it using `--update`. If
this is not specified but the file already exists, the script will avoid overwriting it and log
a message to the console.

Using `--pr`, you can also open a draft pull request from the branch, optionally supplying a
title via `--pr-title`.


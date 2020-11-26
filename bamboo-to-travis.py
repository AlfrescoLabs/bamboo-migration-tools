import getopt
import os
import re
import sys

from datetime import datetime
from github import Github, GithubException, UnknownObjectException, InputGitAuthor

from lib.bamboo import LinkedRepositoriesList, configure_yaml_loader, parse_yml
from lib.config import get_or_create as get_or_create_config
from lib.travis import generate_yaml as generate_travis_yaml

LINKED_REPOSITORIES_CSV_FILE = 'repositories.csv'
CONFIG_FILE = 'config.ini'

input_dir = None
input_file = None
run_datetime = datetime.now()


if len(sys.argv) > 1:
    optlist, args = getopt.getopt(sys.argv[1:], '', ['base-branch=', 'branch=', 'commit-title=', 'commit-desc=', 'update', 'pr', 'pr-title='])
    opts = dict(optlist)
else:
    opts, args = {}, []

if len(args) > 0:
    input_file = args[0]
else:
    input_dir = 'plans'

GITHUB_CONFIG_FIELDS = (
    ('user.name', 'Please enter your full name to be used for Git commits: '),
    ('user.email', 'Please enter your email address to be used for Git commits: '),
    ('user.token', 'Please enter the Github organisation ID: '),
    ('organization', 'Please enter your Github personal access token (must be authorized for the specified organisation: '),
)

def process_file(file_path):
    with open(file_path, 'r') as bamboo_yml_file:
        return parse_yml(bamboo_yml_file)

def process_directory(dir_path):
    all_plans = []
    for yaml_file in sorted(os.listdir(dir_path)):
        bamboo_plan = process_file(os.path.join(dir_path, yaml_file))
        if bamboo_plan is not None:
            all_plans.append(bamboo_plan)
    return all_plans

def header_yaml(plan):
    header_lines = ['# Auto-generated .travis.yml file',
        '# Generated %s from Bamboo build plan %s-%s' % (run_datetime.strftime('%Y-%m-%d %H:%M:%S'), plan.project['key']['key'], plan.key['key']),
        '']
    return header_lines

try:
    config = get_or_create_config(CONFIG_FILE, 'github.com', GITHUB_CONFIG_FIELDS)
    github_org = config['organization']
    gh = Github(config['user.token'])
    linked_repositories = LinkedRepositoriesList(LINKED_REPOSITORIES_CSV_FILE)
    configure_yaml_loader()

    plan_context = {'linked_repositories': linked_repositories}
    if input_dir is not None:
        target_plans = [ plan for plan in process_directory(input_dir) if plan.enabled is True and len(plan.repositories) == 1 ]
        plans_by_repo = {}
        gh_org = gh.get_organization(github_org)
        for plan in target_plans:
            git_path = plan.get_default_repository_definition().github_path(plan_context)
            if not git_path in plans_by_repo:
                plans_by_repo[git_path] = []
            plans_by_repo[git_path].append(plan)
        for git_path, plans in plans_by_repo.items():
            if len(plans) == 1 and git_path.startswith('%s/' % (github_org)):
                source_plan = plans[0]
                gh_repo = gh_org.get_repo(git_path.split('/')[1])
                if not gh_repo.archived and not gh_repo.fork:
                    has_travis_file = True
                    try:
                        travis_yml = gh_repo.get_contents('.travis.yml')
                    except UnknownObjectException:
                        # No .travis.yml found
                        has_travis_file = False
                    if not has_travis_file:
                        print('%s-%s %s' % (source_plan.project['key']['key'], source_plan.key['key'], git_path))
    elif input_file is not None:
        plan = process_file(input_file)
        output_lines = header_yaml(plan) + generate_travis_yaml(plan, plan_context)
        yml_content = '\n'.join(output_lines) + '\n'
        committer = InputGitAuthor(name=config['user.name'], email=config['user.email'])
        if len(args) > 1:
            branch_name = opts.get('--branch', 'dev-travis-migration')
            pr_title = opts.get('--pr-title', 'Add .travis.yml')
            default_commit_message = 'Add .travis.yml' if '--update' not in opts else 'Update .travis.yml'
            commit_message = opts.get('--commit-title', default_commit_message)
            if '--commit-desc' in opts:
                commit_message += '\n\n%s' % (opts.get('--commit-desc'))
            git_project_ref = args[1]
            git_match = re.match('(?:https://github.com)?/?([\w_-]+)/([\w_-]+)', git_project_ref)
            if not git_match:
                print('Unable to find Github project %s' % (git_project_ref))
                exit(1)
            org_name = git_match.group(1)
            repo_name = git_match.group(2)
            file_name = '.travis.yml'
            try:
                repo = gh.get_organization(org_name).get_repo(repo_name)
                base_branch_name = opts.get('--base-branch', 'master')
                master_branch = repo.get_branch(base_branch_name)
                try:
                    new_branch = repo.get_git_ref('heads/' + branch_name)
                except UnknownObjectException:
                    ref_name = 'refs/heads/' + branch_name
                    new_branch = repo.create_git_ref(ref=ref_name, sha=master_branch.commit.sha)
                try:
                    yml_file = repo.create_file(file_name, message=commit_message, content=yml_content, branch=branch_name, committer=committer, author=committer)
                    print('Created file %s on branch %s' % (file_name, new_branch.url))
                except GithubException as file_exception:
                    if file_exception.status == 422: # File exists
                        if '--update' in opts:
                            file_blob = repo.get_contents(file_name, ref='heads/' + branch_name)
                            yml_file = repo.update_file(file_name, message=commit_message, content=yml_content, sha=file_blob.sha, branch=branch_name, committer=committer, author=committer)
                            print('Updated file %s on branch %s' % (file_name, new_branch.url))
                        else:
                            print('File %s already exists, must specify --update to update it' % (file_name))
                            exit(1)
                new_branch.edit(yml_file['commit'].sha)
                if 'pr' in opts:
                    pr = repo.create_pull(pr_title, '', base=base_branch_name, head=branch_name, draft=True)
                    print('Opened pull request %s' % (pr.html_url))
            except UnknownObjectException:
                print('Unable to find repository %s, check it exists and your user account has access' % (git_project_ref))
        else:
            print(yml_content)

except KeyboardInterrupt:
    print('KeyboardInterrupt')

        

import os
import sys

from datetime import datetime
from github import Github, UnknownObjectException, InputGitAuthor

from lib.bamboo import LinkedRepositoriesList, configure_yaml_loader, parse_yml
from lib.config import get_or_create as get_or_create_config
from lib.travis import generate_yaml as generate_travis_yaml

LINKED_REPOSITORIES_CSV_FILE = 'repositories.csv'
CONFIG_FILE = 'config.ini'

input_dir = None
input_file = None
run_datetime = datetime.now()

if len(sys.argv) > 1:
    input_file = sys.argv[1]
else:
    input_dir = 'plans'
if len(sys.argv) > 2:
    output_file = sys.argv[2]

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
        if len(sys.argv) > 2:
            branch_name = 'dev-travis-migration'
            pr_title = 'Add .travis.yml'
            commit_message = 'Add .travis.yml'
            if len(sys.argv) > 3:
                commit_message += '\n\nRefs %s' % (sys.argv[3])
            git_project = sys.argv[2]
            org_name, repo_name = git_project.split('/')
            repo = gh.get_organization(org_name).get_repo(repo_name)
            base_branch_name = 'master'
            master_branch = repo.get_branch(base_branch_name)
            repo.create_git_ref(ref='refs/heads/' + branch_name, sha=master_branch.commit.sha)
            yml_file = repo.create_file('.travis.yml', message=commit_message, content=yml_content, branch=branch_name, committer=committer, author=committer)
            pr = repo.create_pull(pr_title, '', base=base_branch_name, head=branch_name, draft=True)
            print('Opened pull request %s' % (pr.html_url))
        else:
            print(yml_content)

except KeyboardInterrupt:
    print('KeyboardInterrupt')

        

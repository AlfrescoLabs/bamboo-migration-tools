import operator
import re

from functools import reduce


# Mapping of Bamboo JVM versions to Travis equivalents
jvm_versions = (
    ('JDK 1.7', 'oraclejdk7'),
    ('JDK 1.8', 'oraclejdk8'),
    ('OpenJDK 11', 'openjdk11'),
)

def translate_jvm_version(bamboo_jvm):
    for bamboo_prefix, travis_jvm in jvm_versions:
        if bamboo_jvm.startswith(bamboo_prefix):
            return travis_jvm
    return None


class CommandGroup():

    def __init__(self, cmds=[], description='', enabled=True):
        self.cmds = cmds
        self.description = description
        self.enabled = enabled

    def __add__(other_group):
        self.cmds += other_group.cmds

    def serialise_lines(self, indent=8):
        prefix = ' ' * indent
        block_prefix = ' ' * (indent + 2)
        output_lines = []
        if self.cmds and self.description:
            output_lines.append('%s# %s' % (prefix, self.description))
        if not self.enabled:
            prefix += '# '
        for cmd in self.cmds:
            if cmd:
                if '\n' not in cmd:
                    output_lines.append('%s- %s' % (prefix, cmd))
                else:
                    output_lines.append('%s- |' % (prefix))
                    for cmd_item in cmd.splitlines():
                        output_lines.append('%s%s' % (block_prefix, cmd_item))
            else:
                output_lines.append('')
        return output_lines

    def replace_cmd_parameters(self, plan, context=None):
        repo_name_to_urls = dict((getattr(repo['repositoryDefinition'], 'parent') or getattr(repo['repositoryDefinition'], 'name'), repo['repositoryDefinition'].git_url(context)) for repo in plan.repositories)
        self.cmds = [re.sub('\[repo\:([\w\.\-_ ]+)\]', lambda match: repo_name_to_urls[match.group(1)], cmd) for cmd in self.cmds]

    @classmethod
    def _replace_repo_parameters(cls, match):
        return '%s' % ()


def jobs_yaml_lines(source_plan, context=None):
    output_lines = []
    task_languages = []
    task_services = []
    task_addons = {}
    name_prefix = '      '
    for stage in source_plan.stages:
        if stage['description']:
            output_lines.append('    # Stage: %s' % (stage['description']))
        if stage['finalStage'] is True:
            output_lines.append('    # BAMBOO FINAL STAGE - SHOULD RUN REGARDLESS OF STATUS OF OTHER STAGES')
        for job in stage['jobs']:
            output_lines.append('    - stage: "%s"' % (stage['name']))
            output_lines.append('%sname: "%s"' % (name_prefix, job['name']))
            all_travis_jobs = {}
            for task in job['tasks']:
                travis_jobs = task.get_jobs()
                all_commands = reduce(operator.add, travis_jobs.values())
                if len(all_commands) == 0:
                    continue
                if hasattr(task, 'get_language'):
                    task_languages.append(task.get_language())
                if hasattr(task, 'get_services'):
                    task_services += task.get_services()
                # Combine jobs from each Bamboo task into a single Travis job
                for phase, cmds in travis_jobs.items():
                    if isinstance(cmds, str):
                        cmds = [cmds]
                    is_enabled = job['enabled'] and getattr(task, 'enabled', True)
                    group = CommandGroup(cmds, getattr(task, 'description', ''), is_enabled)
                    group.replace_cmd_parameters(source_plan, context)
                    all_travis_jobs[phase] = all_travis_jobs.get(phase, []) + [group]

            if job['artifacts']:
                task_addons['artifacts'] = True
                artifacts_cmds = []
                for artifact in job['artifacts']:
                    artifact_path = artifact['copyPattern']
                    if artifact['location']:
                        artifact_path = artifact['location'] + '/' + artifact_path
                    artifacts_cmds.append('artifacts upload %s' % (artifact_path,))
                group = CommandGroup(artifacts_cmds)
                group.replace_cmd_parameters(source_plan, context)
                all_travis_jobs['after_script'] = all_travis_jobs.get('after_script', []) + [group]

            for phase, cmd_groups in all_travis_jobs.items():
                phase_prefix = '      ' if job['enabled'] else '      # '
                output_lines.append('%s%s:' % (phase_prefix, phase))
                for cmd_group in cmd_groups:
                    output_lines.extend(cmd_group.serialise_lines())
                    
    return output_lines, task_languages, task_services, task_addons

def generate_yaml(plan, context=None):
    output_lines = []
    job_output_lines, job_languages, job_services, job_addons = jobs_yaml_lines(plan, context)
    if len(job_languages):
        language_names = [ language[0] for language in job_languages ]
        for travis_language_name in ['java', 'node_js']:
            if travis_language_name in language_names:
                output_lines.append('language: %s' % (travis_language_name))
                output_lines.append('')
                if travis_language_name == 'java':
                    mentioned_jdks = set([ language[1] for language in job_languages if language[0] == 'java' ])
                    if len(mentioned_jdks) > 1:
                        print('WARNING: Multiple JDK versions spefified: %s' % (mentioned_jdks))
                    travis_jdk = dict(jvm_versions).get(sorted(list(mentioned_jdks))[-1])
                    output_lines.append('jdk:')
                    output_lines.append('  - %s' % (travis_jdk))
                    output_lines.append('')
                elif travis_language_name == 'node_js':
                    mentioned_runtimes = set([ language[1] for language in job_languages if language[0] == 'node_js' ])
                    if len(mentioned_jdks) > 1:
                        raise UnsupportedTaskConfiguration('Multiple Node.js versions spefified: %s' % (mentioned_runtimes))
                    travis_node_js = list(mentioned_runtimes)[0].replace('Node.js').strip()
                    output_lines.append('node_js:')
                    output_lines.append('  - %s' % (travis_node_js))
                    output_lines.append('')
                break
    output_lines.append('dist: xenial')
    output_lines.append('')
    if len(job_services):
        output_lines.append('services:')
        for service_name in job_services:
            output_lines.append('  - %s' % service_name)
        output_lines.append('')
    if len(job_addons):
        output_lines.append('addons:')
        for addon_name, addon_value in job_addons.items():
            output_lines.append(('  %s: %s' % (addon_name, addon_value)).lower())
        output_lines.append('')
    output_lines.append('stages:')
    for stage in plan.stages:
        output_lines.append('  - name: %s' % (stage['name']))
        if stage['manualStage'] is True:
            output_lines.append('    if: fork = false AND (branch = master OR branch =~ /support\/.*/) AND type != pull_request AND commit_message !~ /\[no-release\]/')
    output_lines.append('')
    output_lines.append('jobs:')
    output_lines.append('  include:')
    output_lines += job_output_lines
    return output_lines
